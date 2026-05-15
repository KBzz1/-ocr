import { useState } from 'react';
import type { CaptureSessionSummary, SystemStatus } from '../../pages/workstation/workstation.types';
import { IconButton } from '../common/IconButton';

type WorkstationHeroProps = {
  systemStatus: SystemStatus;
  currentSession: CaptureSessionSummary | null;
  isSystemReady?: boolean;
  isCreatingSession?: boolean;
  createError?: string | null;
  isRetryingSystem?: boolean;
  onRetrySystem?: () => void;
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
  systemStatus,
  currentSession,
  isSystemReady = true,
  isCreatingSession = false,
  createError = null,
  isRetryingSystem = false,
  onRetrySystem = () => undefined,
  onNewCapture,
  onViewQr
}: WorkstationHeroProps) {
  const [endSessionHint, setEndSessionHint] = useState(false);
  const statusTitle =
    systemStatus.startup === 'running'
      ? '系统已启动'
      : systemStatus.startup === 'error'
        ? systemStatus.message ?? '系统状态异常'
        : '正在检查服务';
  const statusPill = systemStatus.startup === 'running' ? '离线运行' : '服务未就绪';

  return (
    <section className="workstation-hero" aria-label="首页核心操作">
      <div className="system-status-panel">
        <div className="system-status-panel__heading">
          <div>
            <p className="section-kicker">系统状态</p>
            <h2>{statusTitle}</h2>
          </div>
          <span className="system-status-panel__pill">{statusPill}</span>
        </div>

        <div className="system-status-grid">
          {systemStatus.items.map((item) => (
            <div className="system-status-item" key={item.id}>
              <span className={`status-dot status-dot--${item.tone}`} aria-hidden="true" />
              <div>
                <div className="system-status-item__label">{item.label}</div>
                <div className="system-status-item__value">{item.value}</div>
              </div>
            </div>
          ))}
        </div>

        {systemStatus.startup === 'error' ? (
          <button className="secondary-action" type="button" disabled={isRetryingSystem} onClick={onRetrySystem}>
            {isRetryingSystem ? '正在重试' : '重试'}
          </button>
        ) : null}
      </div>

      <div className="new-capture-panel">
        <div>
          <p className="section-kicker">新建采集</p>
          <h2>开始新的病历采集</h2>
          <p>
            使用手机扫码拍摄病历文书页面，上传后进入本地解析与人工核验流程。
          </p>
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
