import { useEffect, useRef, useState, type ReactNode } from 'react';

import { getReview, reopenReview, saveReview, type ReviewField, type ReviewPayload, type ReviewResult } from '../../api/review';
import { completeTask, getTaskDetail, getTasks, renameTask, retryTaskProcessing, type TaskDetail, type TaskStatus, type TaskSummary } from '../../api/tasks';
import { ExportPanel } from '../../components/export/ExportPanel';
import { FieldList } from '../../components/review/FieldList';
import { ReviewSourcePanel, type SourceMessage } from '../../components/review/ReviewSourcePanel';
import { getTaskStatusLabel, taskStatusMeta } from '../../styles/status';
import { buildReviewPath } from '../../app/routes';
import { WorkstationLayout } from '../../components/layout/WorkstationLayout';
import './review.css';

type ReviewPageProps = {
  taskId?: string;
  demoPayload?: ReviewPayload;
};

function getTaskIdFromPath() {
  const match = window.location.pathname.match(/^\/tasks\/([^/]+)\/review\/?$/);
  return match ? decodeURIComponent(match[1]) : '1';
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

function stripOcrMarkup(text: string) {
  return text
    .replace(/<br\s*\/?>/gi, '\n')
    .replace(/<\/(div|p|tr|li|h[1-6]|section|article|table)>/gi, '\n')
    .replace(/<[^>]+>/g, '')
    .replace(/&nbsp;/g, ' ')
    .replace(/&lt;/g, '<')
    .replace(/&gt;/g, '>')
    .replace(/&amp;/g, '&')
    .replace(/[ \t]+\n/g, '\n')
    .replace(/\n{3,}/g, '\n\n')
    .trim();
}

function buildDemoTaskDetail(taskId: string, payload: ReviewPayload): TaskDetail {
  return {
    task_id: taskId,
    display_name: taskId,
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
    display_name: taskId,
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
  const [taskOptions, setTaskOptions] = useState<TaskSummary[]>([]);
  const [message, setMessage] = useState<string | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [selectedPageId, setSelectedPageId] = useState<string | null>(null);
  const [selectedFieldKey, setSelectedFieldKey] = useState<string | null>(null);
  const [saveStatus, setSaveStatus] = useState<'idle' | 'dirty' | 'saving' | 'saved' | 'failed'>('idle');
  const [isCompleting, setIsCompleting] = useState(false);
  const [isRetrying, setIsRetrying] = useState(false);
  const [isRenaming, setIsRenaming] = useState(false);
  const [renameDraft, setRenameDraft] = useState('');

  useEffect(() => {
    let isCurrent = true;
    setIsLoading(true);
    setMessage(null);
    setReview(null);
    setFields([]);
    setTaskDetail(null);

    if (!demoPayload) {
      getTasks()
        .then((tasks) => {
          if (isCurrent) setTaskOptions(tasks);
        })
        .catch(() => {
          if (isCurrent) setTaskOptions([]);
        });
    }

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
    return currentFields.map((field) => ({ ...field, status: 'confirmed' as const }));
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

  async function handleMarkUnreviewed() {
    if (savingRef.current || completingRef.current) return;
    try {
      const resetFields = fields.map((field) => ({ ...field, status: 'unreviewed' as const }));
      const savedFields = await saveFields(resetFields);
      if (!savedFields) return;
      if (!demoPayload) {
        await reopenReview(taskId);
      }
      setStatus('review');
      setTaskDetail((current) => current ? { ...current, status: 'review' } : current);
      setMessage('已标记为未审核');
    } catch (error) {
      setSaveStatus('failed');
      setMessage(error instanceof Error ? error.message : '标记未审核失败');
    }
  }

  function handleFieldsChange(nextFields: ReviewField[]) {
    setFields(nextFields);
    setSaveStatus('dirty');
  }

  function handleToggleFieldReviewed(field: ReviewField) {
    setFields((currentFields) =>
      currentFields.map((currentField) =>
        currentField.field_key === field.field_key
          ? {
              ...currentField,
              status: currentField.status === 'confirmed' ? ('unreviewed' as const) : ('confirmed' as const),
            }
          : currentField,
      ),
    );
    setSaveStatus('dirty');
  }

  function handleTaskSwitch(nextTaskId: string) {
    if (!nextTaskId || nextTaskId === taskId) return;
    window.location.href = buildReviewPath(nextTaskId);
  }

  async function handleRetryProcessing() {
    if (isRetrying) return;
    setIsRetrying(true);
    try {
      const task = await retryTaskProcessing(taskId);
      setStatus(task.status);
      setTaskDetail((current) => current ? { ...current, ...task } : { ...task, display_name: taskId, created_at: '', page_count: 0 });
      setMessage('已提交重新处理');
    } catch (error) {
      setMessage(error instanceof Error ? error.message : '重新处理失败，请重试');
    } finally {
      setIsRetrying(false);
    }
  }

  const displayName = taskDetail?.display_name ?? taskId;

  function handleStartRename() {
    if (demoPayload) return;
    setRenameDraft(displayName);
    setIsRenaming(true);
  }

  async function handleCommitRename() {
    const trimmed = renameDraft.trim();
    setIsRenaming(false);
    if (!trimmed || trimmed === displayName) return;
    try {
      const updated = await renameTask(taskId, trimmed);
      setTaskDetail((current) => current ? { ...current, display_name: updated.display_name } : current);
      setTaskOptions((current) =>
        current.map((t) => t.task_id === taskId ? { ...t, display_name: updated.display_name } : t)
      );
    } catch {
      setMessage('重命名失败');
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
    return renderShell(
      <div className="review-readonly-panel">
        <h2>正在加载任务详情</h2>
        <p>请稍候，正在获取任务信息...</p>
      </div>
    );
  }

  if (!taskDetail && !review) {
    return renderShell(
      <p role="alert" className="review-alert review-alert--danger">{message ?? '审核数据加载失败'}</p>
    );
  }

  const taskImages = taskDetail?.images ?? [];
  const reviewPages = review?.pages ?? [];
  const pages = taskImages.length > 0
    ? taskImages.map((img) => {
        const rp = reviewPages.find((p) => p.page_id === img.page_id);
        return {
          page_id: img.page_id,
          page_no: img.page_no ?? 1,
          preview_url: img.preview_url ?? img.image_url,
          image_url: img.image_url,
          parsed_text: rp?.parsed_text
        };
      })
    : reviewPages;
  const selectedPage = pages.find((page) => page.page_id === selectedPageId) ?? pages[0] ?? null;
  const mergedOcrText = stripOcrMarkup(review?.ocr_text ?? pages.map((page) => page.parsed_text ?? '').filter(Boolean).join('\n'));
  const visibleOcrText = mergedOcrText;
  const selectedField = fields.find((field) => field.field_key === selectedFieldKey) ?? fields[0] ?? null;
  const selectedEvidenceText = selectedField?.evidence?.find((item) => item.text)?.text;
  const modifiedFieldCount = fields.filter((field) => field.status === 'modified').length;
  const pendingReviewFieldCount = fields.filter((field) => field.status !== 'confirmed').length;
  const confirmedFieldCount = fields.filter((field) => field.status === 'confirmed').length;
  const sourceMessage: SourceMessage | null = selectedField
      ? selectedEvidenceText
      ? visibleOcrText.includes(selectedEvidenceText)
        ? { kind: 'located', text: '点击字段可定位原文', evidenceText: selectedEvidenceText }
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
  const canReview = canLoadReview(effectiveStatus) && Boolean(review);

  return renderShell(
    <>
      <section className="review-task-card" aria-label="任务信息">
        <div className="review-task-card__media">
          <div className="review-task-card__media-heading">
            <h2>采集图片</h2>
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
                      <span>{page.page_no}</span>
                    )}
                  </button>
                ))}
              </div>
            ) : null}
            <div className="review-document-stage">
              {selectedPage?.preview_url || selectedPage?.image_url ? (
                <img
                  src={selectedPage.preview_url ?? selectedPage.image_url}
                  alt={`第 ${selectedPage.page_no} 页原图`}
                  onError={(e) => {
                    const el = e.currentTarget;
                    el.style.display = 'none';
                    const err = document.createElement('p');
                    err.className = 'review-empty';
                    err.textContent = '图片加载失败';
                    el.parentNode?.insertBefore(err, el);
                  }}
                />
              ) : (
                <p className="review-empty">图片加载失败</p>
              )}
            </div>
          </div>
        </div>

        <div className="review-task-card__body">
          <div className="review-task-card__topline">
            <div>
              <p className="review-detail-card__label">当前任务</p>
              {isRenaming ? (
                <input
                  className="review-task-name-input"
                  value={renameDraft}
                  autoFocus
                  onChange={(e) => setRenameDraft(e.target.value)}
                  onBlur={() => void handleCommitRename()}
                  onKeyDown={(e) => {
                    if (e.key === 'Enter') { e.preventDefault(); void handleCommitRename(); }
                    if (e.key === 'Escape') setIsRenaming(false);
                  }}
                />
              ) : (
                <h1 className="review-task-name" onClick={handleStartRename} title="点击重命名">
                  {displayName}
                </h1>
              )}
            </div>
            <div className="review-status-pill" data-tone={statusMeta.tone}>
              {demoPayload ? <span className="review-demo-label">演示样本</span> : null}
              {getTaskStatusLabel(effectiveStatus)}
            </div>
          </div>

          <label className="review-task-switch">
            <span>切换任务</span>
            <select
              aria-label="切换任务"
              value={taskId}
              onChange={(event) => handleTaskSwitch(event.currentTarget.value)}
              disabled={demoPayload ? true : false}
            >
              <option value={taskId}>{displayName}</option>
              {taskOptions
                .filter((task) => task.task_id !== taskId)
                .map((task) => (
                  <option key={task.task_id} value={task.task_id}>
                    {task.display_name ?? task.task_id} · {getTaskStatusLabel(task.status)}
                  </option>
                ))}
            </select>
          </label>

          <div className="review-task-metrics" aria-label="审核摘要">
            <div>
              <span>创建时间</span>
              <strong>{formatDateTime(detail?.created_at)}</strong>
            </div>
            <div>
              <span>页数</span>
              <strong>{detail?.page_count ?? pages.length} 页</strong>
            </div>
            <div>
              <span>当前进度</span>
              <strong>{detailStageLabel}</strong>
            </div>
            <div>
              <span>字段</span>
              <strong>{fields.length}</strong>
            </div>
            <div className="is-warn">
              <span>待确认</span>
              <strong>{pendingReviewFieldCount}</strong>
            </div>
            <div className="is-info">
              <span>已修改</span>
              <strong>{modifiedFieldCount}</strong>
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
            {canReview ? (
              <>
                <button type="button" onClick={() => void handleSave()} disabled={saveStatus === 'saving' || isCompleting}>
                  保存修改
                </button>
                {effectiveStatus === 'done' ? (
                  <button type="button" onClick={() => void handleMarkUnreviewed()} disabled={saveStatus === 'saving' || isCompleting}>
                    标记未审核
                  </button>
                ) : (
                  <button
                    type="button"
                    className="review-confirm-button"
                    onClick={() => void handleComplete()}
                    disabled={isCompleting || saveStatus === 'saving'}
                  >
                    {isCompleting ? '确认中' : '一键审核'}
                  </button>
                )}
                {effectiveStatus === 'done' ? (
                  <ExportPanel task={{ task_id: taskId, status: effectiveStatus, export_summary: detail?.export_summary }} />
                ) : null}
              </>
            ) : null}
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
        </div>
      </section>

      {message ? <p role="status" className="review-alert">{message}</p> : null}

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
          <section className="review-panel review-panel--ocr" aria-label="OCR 文本">
            <div className="review-panel__heading">
              <h2>OCR 合并文本</h2>
              <span>{pages.length} 页合并</span>
            </div>
            <ReviewSourcePanel text={visibleOcrText || '无 OCR 文本'} sourceMessage={sourceMessage} />
          </section>

          <section className="review-panel review-panel--fields" aria-label="结构化字段">
            <div className="review-panel__heading">
              <div>
                <h2>字段校对</h2>
              </div>
              <span>{fields.length} 个字段，{confirmedFieldCount} 个已确认</span>
            </div>
            <FieldList
              fields={fields}
              fieldGroups={review?.field_groups}
              selectedFieldKey={selectedFieldKey}
              onChange={handleFieldsChange}
              onFocusField={handleFocusField}
              onToggleReviewed={handleToggleFieldReviewed}
            />
          </section>
        </div>
      )}
    </>
  );
}
