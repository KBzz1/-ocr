import type { MouseEvent, ReactNode } from 'react';

import chongqingLogo from '../../assets/logos/chongqing-university-logo.webp';
import xinqiaoLogo from '../../assets/logos/xinqiao-hospital-logo.jpg';
import { appRoutes } from '../../app/routes';
import { IconButton } from '../common/IconButton';
import '../workstation/workstation.css';

const baseNavigationItems = [
  { id: appRoutes.workstation.id, label: '工作台总览', href: appRoutes.workstation.path },
  { id: appRoutes.tasks.id, label: '任务管理', href: appRoutes.tasks.path }
];

type WorkstationLayoutProps = {
  children: ReactNode;
  activeRouteId?: 'workstation' | 'tasks' | 'review';
  reviewTaskHref?: string;
  headerKicker?: string;
  headerTitle?: string;
  systemStatus?: {
    tone: 'success' | 'warning' | 'danger' | 'neutral';
    title: string;
    subtitle: string;
  };
  isRetryingSystem?: boolean;
  onRetrySystem?: () => void;
};

function navigateWithinApp(event: MouseEvent<HTMLAnchorElement>, href: string) {
  if (event.defaultPrevented || event.button !== 0 || event.metaKey || event.ctrlKey || event.shiftKey || event.altKey) {
    return;
  }

  event.preventDefault();
  window.history.pushState({}, '', href);
  window.dispatchEvent(new PopStateEvent('popstate'));
}

export function WorkstationLayout({
  children,
  activeRouteId = 'workstation',
  reviewTaskHref,
  headerKicker = '工作台总览',
  headerTitle = '病历文书结构化采集',
  systemStatus = {
    tone: 'success',
    title: '系统已启动',
    subtitle: '正在运行中'
  },
  isRetryingSystem = false,
  onRetrySystem
}: WorkstationLayoutProps) {
  const navigationItems = reviewTaskHref
    ? [
        ...baseNavigationItems,
        { id: appRoutes.review.id, label: '人工审核', href: reviewTaskHref }
      ]
    : baseNavigationItems;
  return (
    <div className="workstation-shell">
      <aside className="workstation-sidebar" aria-label="工作站导航">
        <div>
          <div className="workstation-brand">
            <div className="workstation-brand__mark" aria-hidden="true">
              文
            </div>
            <div>
              <div className="workstation-brand__title">病历采集工作站</div>
              <div className="workstation-brand__subtitle">本地化部署版</div>
            </div>
          </div>

          <nav className="workstation-nav" aria-label="主要模块">
            {navigationItems.map((item) => (
              <a
                aria-current={item.id === activeRouteId ? 'page' : undefined}
                className={`workstation-nav__item${item.id === activeRouteId ? ' is-active' : ''}`}
                href={item.href}
                key={item.href}
                onClick={(event) => navigateWithinApp(event, item.href)}
              >
                <span className="workstation-nav__icon" aria-hidden="true" />
                <span>{item.label}</span>
              </a>
            ))}
          </nav>
        </div>

        <div className={`workstation-sidebar__status workstation-sidebar__status--${systemStatus.tone}`}>
          <span className={`status-dot status-dot--${systemStatus.tone}`} aria-hidden="true" />
          <div>
            <div className="workstation-sidebar__status-title">{systemStatus.title}</div>
            <div className="workstation-sidebar__status-subtitle">{systemStatus.subtitle}</div>
          </div>
          {systemStatus.tone === 'danger' && onRetrySystem ? (
            <button
              className="workstation-sidebar__status-retry"
              disabled={isRetryingSystem}
              type="button"
              onClick={onRetrySystem}
            >
              {isRetryingSystem ? '重试中' : '重试'}
            </button>
          ) : null}
        </div>
      </aside>

      <div className="workstation-main">
        <header className="workstation-header">
          {headerKicker || headerTitle ? (
            <div>
              {headerKicker ? <p className="workstation-header__kicker">{headerKicker}</p> : null}
              {headerTitle ? <h1>{headerTitle}</h1> : null}
            </div>
          ) : (
            <div aria-hidden="true" />
          )}

          <div className="workstation-header__actions">
            <div className="workstation-header__logos" aria-label="合作单位">
              <img src={chongqingLogo} alt="重庆大学" />
              <img src={xinqiaoLogo} alt="新桥医院" />
            </div>
            <IconButton label="帮助中心" variant="soft">
              ?
            </IconButton>
          </div>
        </header>

        {children}
      </div>
    </div>
  );
}
