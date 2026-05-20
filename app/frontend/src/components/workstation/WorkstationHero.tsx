import { useState } from 'react';
import captureIllustration from '../../assets/illustrations/phone-qr-capture.png';
import type { TaskUploadSummary } from '../../pages/workstation/workstation.types';
import { IconButton } from '../common/IconButton';

type WorkstationHeroProps = {
  currentTask: TaskUploadSummary | null;
  isSystemReady?: boolean;
  isCreatingSession?: boolean;
  createError?: string | null;
  onNewCapture: () => void;
  onViewQr: () => void;
};

export function WorkstationHero({
  currentTask,
  isSystemReady = true,
  isCreatingSession = false,
  createError = null,
  onNewCapture,
  onViewQr
}: WorkstationHeroProps) {
  const [endSessionHint, setEndSessionHint] = useState(false);

  return (
    <section className="workstation-hero" aria-label="首页核心操作">
      <div className="new-capture-panel">
        <div className="new-capture-panel__content">
          <img className="capture-illustration" src={captureIllustration} alt="" aria-hidden="true" />
          <div>
            <h2>开始新的病历采集</h2>
            <p>手机扫码拍摄，电脑端核验导出。</p>
          </div>
        </div>
        <button
          className="primary-action"
          disabled={!isSystemReady || isCreatingSession}
          type="button"
          onClick={onNewCapture}
        >
          <span aria-hidden="true">+</span>
          {isCreatingSession ? '正在创建' : '新建任务'}
        </button>
        {createError ? (
          <p className="inline-error" role="alert">
            {createError}
          </p>
        ) : null}
      </div>

      <div className="current-session-panel">
        <div className="panel-title-row">
          <div>
            <p className="section-kicker">当前任务</p>
            <h2>手机上传入口</h2>
          </div>
          <span
            className={`session-indicator${currentTask ? ' session-indicator--active' : ''}`}
            aria-hidden="true"
          />
        </div>

        {currentTask ? (
          <div className="session-summary">
            <div>
              <div className="session-summary__state">
                上传任务已创建
              </div>
              <div className="session-summary__meta">
                {currentTask.id} · 已上传 {currentTask.uploadedPages} 张图片
              </div>
            </div>
            <div className="session-summary__actions">
              <button className="secondary-action" type="button" onClick={onViewQr}>
                查看二维码
              </button>
            </div>
            {endSessionHint ? (
              <p className="inline-hint">请在手机端点击完成上传，然后回到电脑端审核。</p>
            ) : null}
          </div>
        ) : (
          <div className="session-empty">
            <IconButton label="暂无连接中的设备" variant="soft">
              +
            </IconButton>
            <div>
              <div className="session-summary__state">暂无上传中的任务</div>
              <div className="session-summary__meta">新建任务后，可在此查看手机上传入口。</div>
            </div>
          </div>
        )}
      </div>
    </section>
  );
}
