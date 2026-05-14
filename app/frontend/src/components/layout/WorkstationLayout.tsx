import type { ReactNode } from 'react';

import chongqingLogo from '../../assets/logos/chongqing-university-logo.webp';
import xinqiaoLogo from '../../assets/logos/xinqiao-hospital-logo.jpg';
import { appRoutes } from '../../app/routes';
import { IconButton } from '../common/IconButton';

const navigationItems = [
  { label: '工作台总览', href: appRoutes.workstation.path },
  { label: '任务管理', href: appRoutes.tasks.path }
];

type WorkstationLayoutProps = {
  children: ReactNode;
};

export function WorkstationLayout({ children }: WorkstationLayoutProps) {
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
                className={`workstation-nav__item${item.href === appRoutes.workstation.path ? ' is-active' : ''}`}
                href={item.href}
                key={item.href}
              >
                <span className="workstation-nav__icon" aria-hidden="true" />
                <span>{item.label}</span>
              </a>
            ))}
          </nav>
        </div>

        <div className="workstation-sidebar__status">
          <span className="status-dot status-dot--neutral" aria-hidden="true" />
          <div>
            <div className="workstation-sidebar__status-title">本地离线环境</div>
            <div className="workstation-sidebar__status-subtitle">状态以首页为准</div>
          </div>
        </div>
      </aside>

      <div className="workstation-main">
        <header className="workstation-header">
          <div>
            <p className="workstation-header__kicker">工作台总览</p>
            <h1>病历文书结构化采集</h1>
          </div>

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
