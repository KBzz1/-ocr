/// <reference types="vite/client" />

import { WorkstationLayout } from '../../components/layout/WorkstationLayout';
import { CaptureQrDialog } from '../../components/workstation/CaptureQrDialog';
import { RecentTasks } from '../../components/workstation/RecentTasks';
import { SystemReminders } from '../../components/workstation/SystemReminders';
import { TaskOverview } from '../../components/workstation/TaskOverview';
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
  currentSession: null,
  tasks: [],
  reminders: []
};

type WorkstationPageProps = {
  data?: WorkstationPageData;
  isQrOpen?: boolean;
  isCreatingSession?: boolean;
  createError?: string | null;
  isSystemReady?: boolean;
  onNewCapture?: () => void;
  onViewQr?: () => void;
  onCloseQr?: () => void;
  onRegenerateQr?: () => void;
};

export function WorkstationPage({
  data = emptyWorkstationData,
  isQrOpen = false,
  isCreatingSession = false,
  createError = null,
  isSystemReady = true,
  onNewCapture = () => undefined,
  onViewQr = () => undefined,
  onCloseQr = () => undefined,
  onRegenerateQr
}: WorkstationPageProps) {
  const pageData = data;
  const regenerateQr = onRegenerateQr ?? onNewCapture;

  return (
    <WorkstationLayout>
      <main className="workstation-content" aria-label="电脑端工作台首页">
        <WorkstationHero
          systemStatus={pageData.systemStatus}
          currentSession={pageData.currentSession}
          isSystemReady={isSystemReady}
          isCreatingSession={isCreatingSession}
          createError={createError}
          onNewCapture={onNewCapture}
          onViewQr={onViewQr}
        />

        <TaskOverview tasks={pageData.tasks} />

        <div className="workstation-lower-grid">
          <RecentTasks tasks={pageData.tasks} />
          <SystemReminders reminders={pageData.reminders} />
        </div>
      </main>

      <CaptureQrDialog
        isOpen={isQrOpen}
        session={pageData.currentSession}
        onClose={onCloseQr}
        onRegenerate={regenerateQr}
      />
    </WorkstationLayout>
  );
}
