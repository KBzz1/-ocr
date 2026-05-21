/// <reference types="vite/client" />

import { WorkstationLayout } from '../../components/layout/WorkstationLayout';
import { CaptureQrDialog } from '../../components/workstation/CaptureQrDialog';
import { RecentTasks } from '../../components/workstation/RecentTasks';
import { SystemReminders } from '../../components/workstation/SystemReminders';
import { WorkstationHero } from '../../components/workstation/WorkstationHero';
import type { WorkstationPageData } from './workstation.types';
import '../../components/workstation/workstation.css';

const emptyWorkstationData: WorkstationPageData = {
  systemStatus: {
    startup: 'offline',
    items: [
      { id: 'startup', label: '启动状态', value: '正在检查服务', tone: 'neutral' },
      { id: 'offline', label: '运行方式', value: '离线运行', tone: 'neutral' },
      { id: 'mobile', label: '手机采集', value: '等待服务就绪', tone: 'neutral' }
    ]
  },
  currentTask: null,
  tasks: [],
  reminders: []
};

type WorkstationPageProps = {
  data?: WorkstationPageData;
  isQrOpen?: boolean;
  isCreatingSession?: boolean;
  createError?: string | null;
  isSystemReady?: boolean;
  isRetryingSystem?: boolean;
  lanAddresses?: string[];
  onRetrySystem?: () => void;
  onNewCapture?: () => void;
  onViewQr?: () => void;
  onCloseQr?: () => void;
};

export function WorkstationPage({
  data = emptyWorkstationData,
  isQrOpen = false,
  isCreatingSession = false,
  createError = null,
  isSystemReady = true,
  isRetryingSystem = false,
  lanAddresses = [],
  onRetrySystem = () => undefined,
  onNewCapture = () => undefined,
  onViewQr = () => undefined,
  onCloseQr = () => undefined
}: WorkstationPageProps) {
  const pageData = data;
  const sidebarStatus =
    pageData.systemStatus.startup === 'running'
      ? { tone: 'success' as const, title: '系统已启动', subtitle: '正在运行中' }
      : pageData.systemStatus.startup === 'error'
        ? {
            tone: 'danger' as const,
            title: pageData.systemStatus.message ?? '系统异常',
            subtitle: '请检查本地服务'
          }
        : { tone: 'neutral' as const, title: '正在检查', subtitle: '等待服务响应' };

  return (
    <WorkstationLayout
      systemStatus={sidebarStatus}
      isRetryingSystem={isRetryingSystem}
      onRetrySystem={onRetrySystem}
    >
      <main className="workstation-content" aria-label="电脑端工作台首页">
        <WorkstationHero
          currentTask={pageData.currentTask}
          isSystemReady={isSystemReady}
          isCreatingSession={isCreatingSession}
          createError={createError}
          onNewCapture={onNewCapture}
          onViewQr={onViewQr}
        />

        <div className="workstation-lower-grid">
          <RecentTasks tasks={pageData.tasks} />
          <SystemReminders reminders={pageData.reminders} />
        </div>
      </main>

      <CaptureQrDialog
        isOpen={isQrOpen}
        task={pageData.currentTask}
        onClose={onCloseQr}
        lanAddresses={lanAddresses}
      />
    </WorkstationLayout>
  );
}
