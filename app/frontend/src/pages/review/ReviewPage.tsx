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

  useEffect(() => {
    let isCurrent = true;
    setIsLoading(true);
    getReview(taskId)
      .then((payload) => {
        if (!isCurrent) return;
        setStatus(payload.status);
        setReview(payload.review_result);
        setFields(payload.review_result.fields);
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

  const ocrText = review.ocr_text ?? review.pages?.map((page) => page.parsed_text ?? '').join('\n') ?? '';

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
        <section className="review-panel" aria-label="任务图片">
          <h2>任务图片</h2>
          {review.pages?.length ? (
            review.pages.map((page) => (
              <div key={page.page_id}>
                <h3>第 {page.page_no} 页</h3>
                {page.preview_url || page.image_url ? (
                  <img src={page.preview_url ?? page.image_url} alt={`第 ${page.page_no} 页原图`} />
                ) : null}
              </div>
            ))
          ) : (
            <p>后端未返回任务图片</p>
          )}
        </section>

        <section className="review-panel" aria-label="OCR 文本">
          <h2>OCR 文本</h2>
          <ReviewSourcePanel text={ocrText || '后端未返回 OCR 文本'} sourceMessage={null} />
        </section>

        <section className="review-panel" aria-label="结构化字段">
          <h2>结构化字段</h2>
          <FieldList fields={fields} onChange={setFields} getStatusLabel={(fieldStatus) => fieldStatusMeta[fieldStatus].label} />
          <button type="button" onClick={() => void handleSave()}>
            保存审核结果
          </button>
          <ExportPanel task={{ task_id: taskId, status }} />
        </section>
      </div>
    </main>
  );
}
