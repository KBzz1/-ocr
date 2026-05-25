import { useEffect, useRef, useState, type ReactNode } from 'react';

import { getReview, saveReview, type ReviewField, type ReviewPayload, type ReviewResult } from '../../api/review';
import { completeTask, getTaskDetail, retryTaskProcessing, type TaskDetail, type TaskStatus } from '../../api/tasks';
import { ExportPanel } from '../../components/export/ExportPanel';
import { FieldList } from '../../components/review/FieldList';
import { ReviewSourcePanel, type SourceMessage } from '../../components/review/ReviewSourcePanel';
import { fieldStatusMeta, getTaskStatusLabel, taskStatusMeta } from '../../styles/status';
import { buildReviewPath } from '../../app/routes';
import { WorkstationLayout } from '../../components/layout/WorkstationLayout';
import './review.css';

type ReviewPageProps = {
  taskId?: string;
  demoPayload?: ReviewPayload;
};

function getTaskIdFromPath() {
  const match = window.location.pathname.match(/^\/tasks\/([^/]+)\/review\/?$/);
  return match ? decodeURIComponent(match[1]) : 'task_001';
}

function formatDateTime(value?: string | null) {
  if (!value) return '时间未知';
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return '时间未知';

  const year = date.getFullYear();
  const month = String(date.getMonth() + 1).padStart(2, '0');
  const day = String(date.getDate()).padStart(2, '0');
  const hour = String(date.getHours()).padStart(2, '0');
  const minute = String(date.getMinutes()).padStart(2, '0');
  return `${year}/${month}/${day} ${hour}:${minute}`;
}

function buildDemoTaskDetail(taskId: string, payload: ReviewPayload): TaskDetail {
  return {
    task_id: taskId,
    status: payload.status,
    created_at: '演示样本',
    page_count: payload.review_result.pages?.length ?? 0,
    processing_summary: {
      stage: 'done',
      status: 'completed',
      label: '处理完成',
      progress_percent: 100
    },
    review_summary: {
      confirmed_count: payload.review_result.fields.filter((field) => field.status === 'confirmed').length,
      total_count: payload.review_result.fields.length
    }
  };
}

function buildReviewTaskDetail(taskId: string, payload: ReviewPayload): TaskDetail {
  return {
    task_id: taskId,
    status: payload.status,
    created_at: '',
    page_count: payload.review_result.pages?.length ?? 0,
    review_summary: {
      confirmed_count: payload.review_result.fields.filter((field) => field.status === 'confirmed').length,
      total_count: payload.review_result.fields.length
    }
  };
}

function canLoadReview(status: TaskStatus) {
  return status === 'review' || status === 'done';
}

export function ReviewPage({ taskId = getTaskIdFromPath(), demoPayload }: ReviewPageProps) {
  const [status, setStatus] = useState<TaskStatus>('review');
  const [taskDetail, setTaskDetail] = useState<TaskDetail | null>(null);
  const [review, setReview] = useState<ReviewResult | null>(null);
  const [fields, setFields] = useState<ReviewField[]>([]);
  const [message, setMessage] = useState<string | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [selectedPageId, setSelectedPageId] = useState<string | null>(null);
  const [selectedFieldKey, setSelectedFieldKey] = useState<string | null>(null);
  const [isOcrVisible, setIsOcrVisible] = useState(false);
  const [ocrMode, setOcrMode] = useState<'page' | 'merged'>('page');
  const [saveStatus, setSaveStatus] = useState<'idle' | 'dirty' | 'saving' | 'saved' | 'failed'>('idle');
  const [isCompleting, setIsCompleting] = useState(false);
  const [isRetrying, setIsRetrying] = useState(false);

  useEffect(() => {
    let isCurrent = true;
    setIsLoading(true);
    setMessage(null);
    setReview(null);
    setFields([]);
    setTaskDetail(null);

    async function loadTask() {
      if (demoPayload) {
        const demoDetail = buildDemoTaskDetail(taskId, demoPayload);
        return { detail: demoDetail, payload: demoPayload };
      }

      let detail: TaskDetail | null = null;
      try {
        detail = await getTaskDetail(taskId);
      } catch {
        detail = null;
      }

      if (detail && !canLoadReview(detail.status)) {
        return { detail, payload: null };
      }

      const payload = await getReview(taskId);
      return { detail: detail ?? buildReviewTaskDetail(taskId, payload), payload };
    }

    loadTask()
      .then(({ detail, payload }) => {
        if (!isCurrent) return;
        setTaskDetail(detail);
        setStatus(detail.status);
        setReview(payload?.review_result ?? null);
        setFields(payload?.review_result.fields ?? []);
        const firstPageId = payload?.review_result.pages?.[0]?.page_id ?? null;
        setSelectedPageId(firstPageId);
        setSelectedFieldKey(payload?.review_result.fields[0]?.field_key ?? null);
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
  }, [demoPayload, taskId]);

  function renderShell(content: ReactNode) {
    return (
      <WorkstationLayout
        activeRouteId="review"
        reviewTaskHref={buildReviewPath(taskId)}
        headerKicker="任务详情"
        headerTitle="任务详情与人工审核"
      >
        <main className="review-page" aria-label="人工审核页">{content}</main>
      </WorkstationLayout>
    );
  }

  function normalizeFieldsForUnifiedReview(currentFields: ReviewField[]) {
    return currentFields.map((field) =>
      field.status === 'unreviewed'
        ? { ...field, status: 'confirmed' as const }
        : field
    );
  }

  const savingRef = useRef(false);
  const completingRef = useRef(false);

  async function saveFields(nextFields: ReviewField[]) {
    if (savingRef.current) return null;
    savingRef.current = true;
    setSaveStatus('saving');
    try {
      if (demoPayload) {
        const nextReview = { ...(review ?? demoPayload.review_result), fields: nextFields };
        setReview(nextReview);
        setFields(nextFields);
        setSaveStatus('saved');
        return nextFields;
      }

      const saved = await saveReview(taskId, nextFields);
      setReview(saved.review_result);
      setFields(saved.review_result.fields);
      setSaveStatus('saved');
      return saved.review_result.fields;
    } finally {
      savingRef.current = false;
    }
  }

  async function handleSave() {
    try {
      await saveFields(fields);
      setMessage(null);
    } catch (error) {
      setSaveStatus('failed');
      setMessage(error instanceof Error ? error.message : '保存失败，请重试');
    }
  }

  async function handleComplete() {
    if (savingRef.current || completingRef.current) return;
    completingRef.current = true;
    setIsCompleting(true);
    try {
      const unifiedFields = normalizeFieldsForUnifiedReview(fields);
      const savedFields = await saveFields(unifiedFields);
      if (!savedFields) return;
      if (demoPayload) {
        setStatus('done');
        setMessage('已完成');
        return;
      }

      const task = await completeTask(taskId);
      setStatus(task.status);
      setTaskDetail((current) => current ? { ...current, ...task } : { ...task });
      setMessage('已完成');
    } catch (error) {
      setSaveStatus('failed');
      setMessage(error instanceof Error ? error.message : '统一审核完成失败');
    } finally {
      completingRef.current = false;
      setIsCompleting(false);
    }
  }

  function handleFieldsChange(nextFields: ReviewField[]) {
    setFields(nextFields);
    setSaveStatus('dirty');
  }

  async function handleRetryProcessing() {
    if (isRetrying) return;
    setIsRetrying(true);
    try {
      const task = await retryTaskProcessing(taskId);
      setStatus(task.status);
      setTaskDetail((current) => current ? { ...current, ...task } : { ...task, created_at: '', page_count: 0 });
      setMessage('已提交重新处理');
    } catch (error) {
      setMessage(error instanceof Error ? error.message : '重新处理失败，请重试');
    } finally {
      setIsRetrying(false);
    }
  }

  const handleSaveRef = useRef(handleSave);
  handleSaveRef.current = handleSave;
  const handleCompleteRef = useRef(handleComplete);
  handleCompleteRef.current = handleComplete;

  useEffect(() => {
    function handleKeyDown(event: KeyboardEvent) {
      const isModifier = event.ctrlKey || event.metaKey;
      if (!isModifier) return;
      if (event.key.toLowerCase() === 's') {
        event.preventDefault();
        void handleSaveRef.current();
      }
      if (event.key === 'Enter') {
        event.preventDefault();
        void handleCompleteRef.current();
      }
    }

    window.addEventListener('keydown', handleKeyDown);
    return () => window.removeEventListener('keydown', handleKeyDown);
  }, []);

  if (isLoading) {
    return renderShell(<>正在加载任务详情</>);
  }

  if (!taskDetail && !review) {
    return renderShell(
      <p role="alert" className="review-alert review-alert--danger">{message ?? '审核数据加载失败'}</p>
    );
  }

  const pages = review?.pages ?? [];
  const selectedPage = pages.find((page) => page.page_id === selectedPageId) ?? pages[0] ?? null;
  const mergedOcrText = review?.ocr_text ?? pages.map((page) => page.parsed_text ?? '').filter(Boolean).join('\n');
  const currentPageOcrText = selectedPage?.parsed_text ?? mergedOcrText;
  const visibleOcrText = ocrMode === 'page' ? currentPageOcrText : mergedOcrText;
  const selectedField = fields.find((field) => field.field_key === selectedFieldKey) ?? fields[0] ?? null;
  const selectedEvidenceText = selectedField?.evidence?.find((item) => item.text)?.text;
  const modifiedFieldCount = fields.filter((field) => field.status === 'modified').length;
  const unreviewedFieldCount = fields.filter((field) => field.status === 'unreviewed').length;
  const confirmedFieldCount = fields.filter((field) => field.status === 'confirmed').length;
  const sourceMessage: SourceMessage | null = selectedField
    ? selectedEvidenceText
      ? visibleOcrText.includes(selectedEvidenceText)
        ? { kind: 'located', text: '已定位来源文本', evidenceText: selectedEvidenceText }
        : { kind: 'missing', text: '来源文本未在当前 OCR 中定位' }
      : { kind: 'unavailable', text: '当前字段未返回来源文本' }
    : null;

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

  const detail = taskDetail ?? (review ? buildReviewTaskDetail(taskId, { task_id: taskId, status, review_result: review }) : null);
  const effectiveStatus = detail?.status ?? status;
  const statusMeta = taskStatusMeta[effectiveStatus];
  const detailProgress = detail?.processing_summary?.progress_percent ?? (effectiveStatus === 'done' || effectiveStatus === 'review' ? 100 : 0);
  const detailStageLabel =
    detail?.processing_summary?.label ??
    (effectiveStatus === 'review' || effectiveStatus === 'done' ? '处理完成' : statusMeta.label);
  const failureReason = effectiveStatus === 'failed'
    ? detail?.error_message || detail?.error_code || '处理失败，请重新处理'
    : null;
  const latestHistory = detail?.status_history?.slice(-3).reverse() ?? [];
  const canReview = canLoadReview(effectiveStatus) && Boolean(review);

  return renderShell(
    <>
      <header className="review-header">
        <div>
          <div className="review-title-line">
            <h1>任务 {taskId}</h1>
          </div>
          <div className="review-status-pill">
            {demoPayload ? <span className="review-demo-label">演示样本</span> : null}
            {getTaskStatusLabel(effectiveStatus)}
          </div>
        </div>
        <div className="review-metrics" aria-label="审核摘要">
          <div>
            <span>页数</span>
            <strong>{pages.length} / {pages.length || 0}</strong>
          </div>
          <div>
            <span>字段</span>
            <strong>{fields.length}</strong>
          </div>
          <div className="is-warn">
            <span>待确认</span>
            <strong>{unreviewedFieldCount}</strong>
          </div>
          <div className="is-info">
            <span>已修改</span>
            <strong>{modifiedFieldCount}</strong>
          </div>
        </div>
        <div className="review-header__actions">
          {saveStatus !== 'idle' ? (
            <span className={`review-save-state review-save-state--${saveStatus}`} aria-live="polite">
              {saveStatus === 'dirty'
                ? '未保存修改'
                : saveStatus === 'saving'
                  ? '保存中'
                  : saveStatus === 'saved'
                    ? '已保存'
                    : '保存失败'}
            </span>
          ) : null}
          <button type="button" onClick={() => void handleSave()} disabled={saveStatus === 'saving' || isCompleting}>
            保存修改
          </button>
          <button
            type="button"
            className="review-confirm-button"
            onClick={() => void handleComplete()}
            disabled={isCompleting || saveStatus === 'saving'}
          >
            {isCompleting ? '确认中' : '确认完成'}
          </button>
        </div>
      </header>

      {message ? <p role="status" className="review-alert">{message}</p> : null}

      <section className="review-detail-card" aria-label="任务详情">
        <div className="review-detail-card__main">
          <div>
            <p className="review-detail-card__label">任务详情</p>
            <strong>{statusMeta.label}</strong>
          </div>
          <div>
            <p className="review-detail-card__label">创建时间</p>
            <strong>{formatDateTime(detail?.created_at)}</strong>
          </div>
          <div>
            <p className="review-detail-card__label">页数</p>
            <strong>{detail?.page_count ?? pages.length} 页</strong>
          </div>
          <div>
            <p className="review-detail-card__label">当前进度</p>
            <strong>{detailStageLabel}</strong>
          </div>
        </div>
        <div className="review-detail-card__progress">
          <span
            aria-label="任务处理进度"
            aria-valuemax={100}
            aria-valuemin={0}
            aria-valuenow={detailProgress}
            role="progressbar"
          >
            <span style={{ width: `${detailProgress}%` }} />
          </span>
        </div>
        {failureReason ? (
          <div className="review-failure-box" role="alert">
            <div>
              <p className="review-detail-card__label">失败原因</p>
              <strong>{failureReason}</strong>
            </div>
            <button type="button" disabled={isRetrying} onClick={() => void handleRetryProcessing()}>
              {isRetrying ? '提交中' : '重新处理'}
            </button>
          </div>
        ) : null}
        {latestHistory.length ? (
          <div className="review-history-strip" aria-label="最近任务动态">
            {latestHistory.map((item, index) => (
              <span key={`${item.changed_at}-${index}`}>
                {formatDateTime(item.changed_at)} · {item.message ?? item.reason ?? item.to_status ?? item.status}
              </span>
            ))}
          </div>
        ) : null}
      </section>

      {!canReview ? (
        <section className="review-readonly-panel" aria-label="任务当前状态">
          <h2>{effectiveStatus === 'failed' ? '任务处理失败' : '任务尚未进入审核'}</h2>
          <p>
            {effectiveStatus === 'failed'
              ? '请根据失败原因检查本地 OCR/结构化模块配置，或重新提交现有图片进行处理。'
              : '任务详情会持续显示当前进度；处理完成后这里会进入字段审核。'}
          </p>
        </section>
      ) : (
        <div className="review-grid">
          <div className="review-source-column">
            <section className="review-panel review-panel--image" aria-label="任务图片">
              <div className="review-panel__heading">
                <h2>原图</h2>
                <span>第 {selectedPage?.page_no ?? 0} 页 / 共 {pages.length} 页</span>
              </div>
              <div className="review-document-shell">
                {pages.length ? (
                  <div className="review-page-tabs" role="tablist" aria-label="任务页码">
                    {pages.map((page) => (
                      <button
                        aria-label={`第 ${page.page_no} 页`}
                        aria-selected={page.page_id === selectedPage?.page_id}
                        key={page.page_id}
                        type="button"
                        onClick={() => setSelectedPageId(page.page_id)}
                      >
                        <span>{page.page_no}</span>
                        {page.preview_url || page.image_url ? (
                          <img src={page.preview_url ?? page.image_url} alt="" />
                        ) : (
                          <span className="review-thumb-placeholder" />
                        )}
                      </button>
                    ))}
                  </div>
                ) : null}
                <div className="review-document-stage">
                  {selectedPage?.preview_url || selectedPage?.image_url ? (
                    <img src={selectedPage.preview_url ?? selectedPage.image_url} alt={`第 ${selectedPage.page_no} 页原图`} />
                  ) : (
                    <div className="review-document-fallback" aria-label="无原图预览">
                      <h3>重庆大学附属新桥医院</h3>
                      <h4>住院病历首页</h4>
                      {(currentPageOcrText || mergedOcrText || '无原图').split('\n').slice(0, 10).map((line, index) => (
                        <p key={`${line}-${index}`}>{line}</p>
                      ))}
                    </div>
                  )}
                </div>
              </div>
            </section>

            <section className={`review-panel review-panel--ocr${isOcrVisible ? ' is-open' : ''}`} aria-label="OCR 文本">
              <div className="review-panel__heading">
                <h2>OCR</h2>
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
                  <ReviewSourcePanel text={visibleOcrText || '无 OCR 文本'} sourceMessage={sourceMessage} />
                </>
              ) : null}
            </section>
          </div>

          <section className="review-panel review-panel--fields" aria-label="结构化字段">
            <div className="review-panel__heading">
              <div>
                <h2>字段校对</h2>
              </div>
              <span>{fields.length} 个字段，{confirmedFieldCount} 个已确认</span>
            </div>
            <FieldList
              fields={fields}
              selectedFieldKey={selectedFieldKey}
              onChange={handleFieldsChange}
              onFocusField={handleFocusField}
              getStatusLabel={(fieldStatus) => fieldStatusMeta[fieldStatus].label}
            />
            <ExportPanel task={{ task_id: taskId, status: effectiveStatus }} />
          </section>
        </div>
      )}
    </>
  );
}
