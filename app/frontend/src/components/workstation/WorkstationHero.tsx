import { useState } from 'react';
import captureIllustration from '../../assets/illustrations/phone-qr-capture.png';
import type { CaptureSessionSummary } from '../../pages/workstation/workstation.types';
import { IconButton } from '../common/IconButton';

type WorkstationHeroProps = {
  currentSession: CaptureSessionSummary | null;
  isSystemReady?: boolean;
  isCreatingSession?: boolean;
  createError?: string | null;
  onNewCapture: () => void;
  onViewQr: () => void;
};

const sessionStatusText: Record<NonNullable<CaptureSessionSummary>['status'], string> = {
  active: '会话进行中',
  expired: '已过期，不可继续上传',
  locked: '采集已完成',
  cancelled: '已取消'
};

export function WorkstationHero({
  currentSession,
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
          {isCreatingSession ? '正在创建' : '新建采集'}
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
            <p className="section-kicker">当前会话</p>
            <h2>当前采集会话</h2>
          </div>
          <span
            className={`session-indicator${currentSession ? ' session-indicator--active' : ''}`}
            aria-hidden="true"
          />
        </div>

        {currentSession ? (
          <div className="session-summary">
            <div>
              <div className="session-summary__state">
                {sessionStatusText[currentSession.status]}
              </div>
              <div className="session-summary__meta">
                已上传 {currentSession.uploadedPages} 页 · 剩余 {currentSession.remainingTimeText}
              </div>
            </div>
            <div className="session-summary__actions">
              <button className="secondary-action" type="button" onClick={onViewQr}>
                查看二维码
              </button>
              <button className="secondary-action" type="button" onClick={() => setEndSessionHint(true)}>
                结束会话
              </button>
            </div>
            {endSessionHint ? (
              <p className="inline-hint">请在手机端点击完成采集；如需作废，请重新生成二维码。</p>
            ) : null}
          </div>
        ) : (
          <div className="session-empty">
            <IconButton label="暂无连接中的设备" variant="soft">
              +
            </IconButton>
            <div>
              <div className="session-summary__state">暂无进行中的采集会话</div>
              <div className="session-summary__meta">新建采集后，可在此查看上传进度。</div>
            </div>
          </div>
        )}
      </div>
    </section>
  );
}
