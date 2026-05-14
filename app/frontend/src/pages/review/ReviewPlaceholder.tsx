import { useEffect, useMemo, useState } from 'react';

import { ApiError } from '../../api/client';
import { confirmReview, getReviewResult, saveReviewField, type ReviewField } from '../../api/review';
import { getTaskDetail, retryTaskProcessing, type TaskDetail } from '../../api/tasks';
import { FieldList } from '../../components/review/FieldList';
import { ReviewSourcePanel, type SourceMessage } from '../../components/review/ReviewSourcePanel';
import { fieldStatusMeta, type FieldStatus } from '../../styles/status';
import './review.css';

type ReviewPageRecord = {
  page_id: string;
  page_no?: number;
  page_index?: number;
  image_url?: string;
  parsed_text?: string;
};

type ReviewTaskDetail = Omit<TaskDetail, 'pages'> & {
  pages?: ReviewPageRecord[];
};

type ReviewPlaceholderProps = {
  taskId?: string;
};

type SaveState = Record<string, boolean>;

function getTaskIdFromPath() {
  const match = window.location.pathname.match(/^\/tasks\/([^/]+)\/review$/);
  return match ? decodeURIComponent(match[1]) : 'task-ready';
}

function getPageLabel(page: ReviewPageRecord, fallbackIndex: number) {
  return `第${page.page_no ?? page.page_index ?? fallbackIndex + 1}页`;
}

function getInitialFieldValue(field: ReviewField) {
  return field.final_value;
}

function getNextStatus(value: string): FieldStatus {
  return value.trim() === '' ? 'empty' : 'modified';
}

function countByStatus(fields: ReviewField[]) {
  return fields.reduce(
    (summary, field) => {
      summary[field.status] += 1;
      return summary;
    },
    { unreviewed: 0, confirmed: 0, modified: 0, suspicious: 0, empty: 0 } satisfies Record<FieldStatus, number>
  );
}

function buildBlockMessage(summary: Record<FieldStatus, number>) {
  const blockers = [
    summary.unreviewed > 0 ? `仍有 ${summary.unreviewed} 个未审核字段` : '',
    summary.suspicious > 0 ? `仍有 ${summary.suspicious} 个存疑字段` : '',
    summary.empty > 0 ? `仍有 ${summary.empty} 个空值字段未确认可接受` : ''
  ].filter(Boolean);

  return blockers.join('，');
}

function getErrorMessage(error: unknown, fallback: string) {
  if (error instanceof ApiError) return error.message;
  return fallback;
}

function getConfirmErrorMessage(error: unknown) {
  if (!(error instanceof ApiError)) return '确认审核失败，请重试';
  const issues = Object.values(error.details).flatMap((value) => {
    if (Array.isArray(value)) return value.map((item) => String(item));
    if (typeof value === 'string') return [value];
    return [];
  });
  return issues.length > 0 ? `${error.message}：${issues.join('；')}` : error.message;
}

export function ReviewPlaceholder({ taskId = getTaskIdFromPath() }: ReviewPlaceholderProps) {
  const [task, setTask] = useState<ReviewTaskDetail | null>(null);
  const [fields, setFields] = useState<ReviewField[]>([]);
  const [selectedPageIndex, setSelectedPageIndex] = useState(0);
  const [textMode, setTextMode] = useState<'page' | 'merged'>('page');
  const [isLoading, setIsLoading] = useState(true);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [saveError, setSaveError] = useState<string | null>(null);
  const [confirmMessage, setConfirmMessage] = useState<string | null>(null);
  const [isConfirming, setIsConfirming] = useState(false);
  const [savingFields, setSavingFields] = useState<SaveState>({});
  const [sourceMessage, setSourceMessage] = useState<SourceMessage | null>(null);

  useEffect(() => {
    let isCurrent = true;
    setIsLoading(true);
    setLoadError(null);
    setFields([]);
    setTask(null);
    setConfirmMessage(null);
    setSourceMessage(null);

    getTaskDetail(taskId)
      .then(async (nextTask) => {
        if (!isCurrent) return;
        setTask(nextTask as ReviewTaskDetail);
        if (nextTask.status === 'failed') return;

        const review = await getReviewResult(taskId);
        if (!isCurrent) return;
        setFields(review.fields);
      })
      .catch((error: unknown) => {
        if (isCurrent) setLoadError(getErrorMessage(error, '审核数据加载失败'));
      })
      .finally(() => {
        if (isCurrent) setIsLoading(false);
      });

    return () => {
      isCurrent = false;
    };
  }, [taskId]);

  const pages = task?.pages ?? [];
  const selectedPage = pages[selectedPageIndex] ?? pages[0];
  const summary = useMemo(() => countByStatus(fields), [fields]);
  const isSavingAnyField = Object.values(savingFields).some(Boolean);

  async function handleSaveField(field: ReviewField, finalValue: string, status: FieldStatus) {
    const previousField = field;
    setSaveError(null);
    setSavingFields((current) => ({ ...current, [field.field_key]: true }));
    setFields((current) =>
      current.map((item) =>
        item.field_key === field.field_key ? { ...item, final_value: finalValue, status } : item
      )
    );

    try {
      const saved = await saveReviewField(taskId, field.field_key, { final_value: finalValue, status });
      setFields((current) =>
        current.map((item) =>
          item.field_key === saved.field_key
            ? { ...item, final_value: saved.final_value, status: saved.status }
            : item
        )
      );
    } catch {
      setFields((current) =>
        current.map((item) => (item.field_key === previousField.field_key ? previousField : item))
      );
      setSaveError('保存失败，请重试');
    } finally {
      setSavingFields((current) => ({ ...current, [field.field_key]: false }));
    }
  }

  function handleEvidence(field: ReviewField) {
    const evidence = field.evidence[0];
    if (!evidence) {
      setSourceMessage({ kind: 'missing', text: '此字段无对应来源文本' });
      return;
    }

    const pageExists = pages.some((page) => {
      const pageNo = page.page_no ?? page.page_index;
      return page.page_id === evidence.page_id || pageNo === evidence.page_no;
    });

    if (!pageExists) {
      setSourceMessage({ kind: 'unavailable', text: '来源页不可用' });
      return;
    }

    if (typeof evidence.page_no === 'number') {
      const nextPageIndex = pages.findIndex((page) => page.page_id === evidence.page_id || page.page_no === evidence.page_no);
      if (nextPageIndex >= 0) setSelectedPageIndex(nextPageIndex);
    }

    setTextMode('page');
    setSourceMessage({
      kind: 'located',
      text: `已定位来源：第${evidence.page_no ?? '?'}页 ${evidence.text ?? ''}`.trim(),
      evidenceText: evidence.text
    });
  }

  async function handleConfirmReview() {
    setConfirmMessage(null);
    const blocker = buildBlockMessage(summary);
    if (blocker) {
      setConfirmMessage(blocker);
      return;
    }

    setIsConfirming(true);
    try {
      await confirmReview(taskId);
      setConfirmMessage('审核已确认');
    } catch (error: unknown) {
      setConfirmMessage(getConfirmErrorMessage(error));
    } finally {
      setIsConfirming(false);
    }
  }

  async function handleRetry() {
    await retryTaskProcessing(taskId);
  }

  if (isLoading) {
    return <main aria-label="人工审核页">正在加载审核数据</main>;
  }

  if (loadError) {
    return (
      <main className="review-page" aria-label="人工审核页">
        <p role="alert" className="review-alert review-alert--danger">
          {loadError}
        </p>
      </main>
    );
  }

  if (task?.status === 'failed') {
    return (
      <main className="review-page" aria-label="人工审核页">
        <div role="alert" className="review-alert review-alert--danger">
          <p>{task.error_message ?? '任务处理失败，不能进入人工审核'}</p>
          <button type="button" onClick={handleRetry}>
            重新处理
          </button>
        </div>
      </main>
    );
  }

  const pageText = selectedPage?.parsed_text ?? '后端未返回当前页解析文本';
  const mergedText = pages.map((page, index) => `${getPageLabel(page, index)}：${page.parsed_text ?? ''}`).join('\n');

  return (
    <main className="review-page" aria-label="人工审核页">
      <header className="review-header">
        <div>
          <p className="review-eyebrow">人工审核</p>
          <h1>任务 {taskId}</h1>
        </div>
        <button
          type="button"
          className="review-confirm-button"
          disabled={isConfirming || isSavingAnyField}
          onClick={handleConfirmReview}
        >
          确认审核
        </button>
      </header>

      <section className="review-summary" aria-label="字段统计">
        <span>未审核 {summary.unreviewed}</span>
        <span>存疑 {summary.suspicious}</span>
        <span>为空 {summary.empty}</span>
        <span>已确认 {summary.confirmed + summary.modified}</span>
      </section>

      {saveError ? (
        <p role="alert" className="review-alert review-alert--danger">
          {saveError}
        </p>
      ) : null}
      {confirmMessage ? (
        <p role="alert" className="review-alert">
          {confirmMessage}
        </p>
      ) : null}

      <div className="review-grid">
        <section className="review-panel" aria-label="原图">
          <div className="review-page-tabs" aria-label="页码切换">
            {pages.map((page, index) => (
              <button
                type="button"
                key={page.page_id}
                aria-pressed={index === selectedPageIndex}
                onClick={() => {
                  setSelectedPageIndex(index);
                  setTextMode('page');
                }}
              >
                {getPageLabel(page, index)}
              </button>
            ))}
          </div>
          {selectedPage?.image_url ? (
            <img src={selectedPage.image_url} alt={`${getPageLabel(selectedPage, selectedPageIndex)}原图`} />
          ) : (
            <p>后端未返回当前页原图</p>
          )}
        </section>

        <section className="review-panel" aria-label="解析文本">
          <div className="review-text-actions">
            <button type="button" aria-pressed={textMode === 'page'} onClick={() => setTextMode('page')}>
              当前页文本
            </button>
            <button type="button" aria-pressed={textMode === 'merged'} onClick={() => setTextMode('merged')}>
              合并文本
            </button>
          </div>
          <ReviewSourcePanel
            text={textMode === 'merged' ? mergedText || '后端返回的合并文本为空' : pageText}
            sourceMessage={sourceMessage}
          />
        </section>

        <section className="review-panel" aria-label="结构化字段">
          <FieldList
            fields={fields}
            savingFields={savingFields}
            onEvidence={handleEvidence}
            onSave={(field, value) => handleSaveField(field, value, getNextStatus(value))}
            onStatus={(field, status) => handleSaveField(field, getInitialFieldValue(field), status)}
            getStatusLabel={(status) => fieldStatusMeta[status].label}
          />
        </section>
      </div>
    </main>
  );
}
