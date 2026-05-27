import type { MouseEvent, ReactNode } from 'react';

import chongqingLogo from '../../assets/logos/chongqing-university-logo.png';
import xinqiaoLogo from '../../assets/logos/xinqiao-hospital-logo.png';
import { appRoutes } from '../../app/routes';
import '../workstation/workstation.css';

const baseNavigationItems = [
  { id: appRoutes.workstation.id, label: '首页', href: appRoutes.workstation.path },
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
  headerKicker = '',
  headerTitle = '',
  systemStatus = {
    tone: 'success',
    title: '系统已启动',
    subtitle: '正在运行中'
  },
  isRetryingSystem = false,
  onRetrySystem
}: WorkstationLayoutProps) {
  const navigationItems = [
    ...baseNavigationItems,
    { id: appRoutes.review.id, label: '任务详情', href: reviewTaskHref ?? appRoutes.review.path }
  ];
  const hasHeaderText = Boolean(headerKicker || headerTitle);

  return (
    <div className="workstation-shell">
      <aside className="workstation-sidebar" aria-label="工作站导航">
        <div>
          <div className="workstation-brand">
            <div className="workstation-brand__logos" aria-label="合作单位">
              <img
                className="workstation-brand__logo workstation-brand__logo--university"
                src={chongqingLogo}
                alt="重庆大学"
              />
              <img
                className="workstation-brand__logo workstation-brand__logo--hospital"
                src={xinqiaoLogo}
                alt="新桥医院"
              />
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
        {hasHeaderText ? (
          <header className="workstation-header">
            <div>
              {headerKicker ? <p className="workstation-header__kicker">{headerKicker}</p> : null}
              {headerTitle ? <h1>{headerTitle}</h1> : null}
            </div>
          </header>
        ) : null}

        {children}
      </div>
    </div>
  );
}
