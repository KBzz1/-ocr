import { useEffect, useState, type ReactNode } from 'react';

import { getReview, saveReview, type ReviewField, type ReviewResult } from '../../api/review';
import { completeTask, type TaskStatus } from '../../api/tasks';
import { ExportPanel } from '../../components/export/ExportPanel';
import { FieldList } from '../../components/review/FieldList';
import { ReviewSourcePanel } from '../../components/review/ReviewSourcePanel';
import { fieldStatusMeta } from '../../styles/status';
import { buildReviewPath } from '../../app/routes';
import { WorkstationLayout } from '../../components/layout/WorkstationLayout';
import './review.css';

type ReviewPageProps = {
  taskId?: string;
};

function getTaskIdFromPath() {
  const match = window.location.pathname.match(/^\/tasks\/([^/]+)\/review\/?$/);
  return match ? decodeURIComponent(match[1]) : 'task_001';
}

export function ReviewPage({ taskId = getTaskIdFromPath() }: ReviewPageProps) {
  const [status, setStatus] = useState<TaskStatus>('review');
  const [review, setReview] = useState<ReviewResult | null>(null);
  const [fields, setFields] = useState<ReviewField[]>([]);
  const [message, setMessage] = useState<string | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [selectedPageId, setSelectedPageId] = useState<string | null>(null);
  const [selectedFieldKey, setSelectedFieldKey] = useState<string | null>(null);
  const [isOcrVisible, setIsOcrVisible] = useState(false);
  const [ocrMode, setOcrMode] = useState<'page' | 'merged'>('page');

  useEffect(() => {
    let isCurrent = true;
    setIsLoading(true);
    getReview(taskId)
      .then((payload) => {
        if (!isCurrent) return;
        setStatus(payload.status);
        setReview(payload.review_result);
        setFields(payload.review_result.fields);
        const firstPageId = payload.review_result.pages?.[0]?.page_id ?? null;
        setSelectedPageId(firstPageId);
        setSelectedFieldKey(payload.review_result.fields[0]?.field_key ?? null);
      })
      .catch(() => {
        if (isCurrent) setMessage('审核数据加载失败');
      })
      .finally(() => {
        if (isCurrent) setIsLoading(false);
      });

    return () => {
      isCurrent = false;
    };
  }, [taskId]);

  function renderShell(content: ReactNode) {
    return (
      <WorkstationLayout
        activeRouteId="review"
        reviewTaskHref={buildReviewPath(taskId)}
        headerKicker="人工审核"
        headerTitle={`任务 ${taskId}`}
      >
        {content}
      </WorkstationLayout>
    );
  }

  async function handleSave() {
    const saved = await saveReview(taskId, fields);
    setReview(saved.review_result);
    setFields(saved.review_result.fields);
    setMessage('已保存');
  }

  async function handleComplete() {
    try {
      const task = await completeTask(taskId);
      setStatus(task.status);
      setMessage('已完成');
    } catch (error) {
      setMessage(error instanceof Error ? error.message : '标记完成失败');
    }
  }

  function handleFieldsChange(nextFields: ReviewField[]) {
    setFields(nextFields);
  }

  function handleFocusField(field: ReviewField) {
    setSelectedFieldKey(field.field_key);
    const evidence = field.evidence?.find((item) => item.page_id || item.page_no);
    if (evidence?.page_id) {
      setSelectedPageId(evidence.page_id);
      return;
    }
    const pageByNo = pages.find((page) => page.page_no === evidence?.page_no);
    if (pageByNo) setSelectedPageId(pageByNo.page_id);
  }

  if (isLoading) {
    return renderShell(<main className="review-page" aria-label="人工审核页">正在加载审核数据</main>);
  }

  if (!review) {
    return renderShell(
      <main className="review-page" aria-label="人工审核页">
        <p role="alert" className="review-alert review-alert--danger">{message ?? '审核数据加载失败'}</p>
      </main>
    );
  }

  const pages = review.pages ?? [];
  const selectedPage = pages.find((page) => page.page_id === selectedPageId) ?? pages[0] ?? null;
  const mergedOcrText = review.ocr_text ?? pages.map((page) => page.parsed_text ?? '').filter(Boolean).join('\n');
  const currentPageOcrText = selectedPage?.parsed_text ?? mergedOcrText;
  const visibleOcrText = ocrMode === 'page' ? currentPageOcrText : mergedOcrText;

  return renderShell(
    <main className="review-page" aria-label="人工审核页">
      <header className="review-header">
        <div>
          <p className="review-eyebrow">人工审核</p>
          <h1>任务 {taskId}</h1>
        </div>
        <button type="button" className="review-confirm-button" onClick={() => void handleComplete()}>
          标记完成
        </button>
      </header>

      {message ? <p role="status" className="review-alert">{message}</p> : null}

      <div className="review-grid">
        <section className="review-panel review-panel--image" aria-label="任务图片">
          <div className="review-panel__heading">
            <h2>任务图片</h2>
            <span>{pages.length ? `共 ${pages.length} 页` : '无页面'}</span>
          </div>
          {pages.length ? (
            <div className="review-page-tabs" role="tablist" aria-label="任务页码">
              {pages.map((page) => (
                <button
                  aria-selected={page.page_id === selectedPage?.page_id}
                  key={page.page_id}
                  type="button"
                  onClick={() => setSelectedPageId(page.page_id)}
                >
                  第 {page.page_no} 页
                </button>
              ))}
            </div>
          ) : null}
          {selectedPage?.preview_url || selectedPage?.image_url ? (
            <img src={selectedPage.preview_url ?? selectedPage.image_url} alt={`第 ${selectedPage.page_no} 页原图`} />
          ) : (
            <p className="review-empty">后端未返回当前页原图</p>
          )}
        </section>

        <section className={`review-panel review-panel--ocr${isOcrVisible ? ' is-open' : ''}`} aria-label="OCR 文本">
          <div className="review-panel__heading">
            <h2>OCR 文本</h2>
            <button type="button" onClick={() => setIsOcrVisible((value) => !value)}>
              {isOcrVisible ? '隐藏 OCR' : '显示 OCR'}
            </button>
          </div>
          {isOcrVisible ? (
            <>
              <div className="review-text-actions" aria-label="OCR 文本范围">
                <button
                  aria-pressed={ocrMode === 'page'}
                  type="button"
                  onClick={() => setOcrMode('page')}
                >
                  当前页
                </button>
                <button
                  aria-pressed={ocrMode === 'merged'}
                  type="button"
                  onClick={() => setOcrMode('merged')}
                >
                  合并文本
                </button>
              </div>
              <ReviewSourcePanel text={visibleOcrText || '后端未返回 OCR 文本'} sourceMessage={null} />
            </>
          ) : null}
        </section>

        <section className="review-panel" aria-label="结构化字段">
          <h2>结构化字段</h2>
          <FieldList
            fields={fields}
            selectedFieldKey={selectedFieldKey}
            onChange={handleFieldsChange}
            onFocusField={handleFocusField}
            getStatusLabel={(fieldStatus) => fieldStatusMeta[fieldStatus].label}
          />
          <button type="button" onClick={() => void handleSave()}>
            保存审核结果
          </button>
          <ExportPanel task={{ task_id: taskId, status }} />
        </section>
      </div>
    </main>
  );
}
