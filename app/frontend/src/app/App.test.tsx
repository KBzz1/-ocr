import { render, screen, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { beforeEach, describe, expect, it } from 'vitest';

import { mockSystemStatus, mockSystemStatusError } from '../../tests/fixtures/system';
import { mockCreateTask, mockCreateTaskError, mockTasks, taskFixtures } from '../../tests/fixtures/tasks';
import { server } from '../../tests/setupTests';
import { buildMobileUploadPath } from './routes';
import { App } from './App';

function renderWorkstation() {
  window.history.pushState({}, '', '/');
  server.use(mockSystemStatus(), mockTasks());
  return render(<App />);
}

describe('Workstation data integration', () => {
  beforeEach(() => {
    window.history.pushState({}, '', '/');
  });

  it('renders mobile upload page for scanned task upload paths', async () => {
    window.history.pushState({}, '', `${buildMobileUploadPath('task_001')}?token=token_001`);
    render(<App />);

    expect(await screen.findByText(/病历文书采集|手机上传/)).toBeTruthy();
    expect(screen.queryByRole('button', { name: /新建任务/ })).toBeNull();
  });

  it('renders backend status errors without a misleading running state', async () => {
    server.use(mockSystemStatusError(), mockTasks([]));
    render(<App />);

    expect(await screen.findByText('系统状态异常')).toBeTruthy();
    expect((screen.getByRole('button', { name: /新建任务/ }) as HTMLButtonElement).disabled).toBe(true);
  });

  it('renders recent task actions without the removed dashboard overview', async () => {
    renderWorkstation();

    expect(await screen.findByText('系统已启动')).toBeTruthy();
    expect(screen.queryByLabelText('任务概览')).toBeNull();

    const table = screen.getByRole('table');
    expect(within(table).getByText('task-ready')).toBeTruthy();
    expect(within(table).getByText('进入审核')).toBeTruthy();
    expect(within(table).getByText('查看原因')).toBeTruthy();
    expect(within(table).getByText('重新处理')).toBeTruthy();
    expect(document.body.textContent ?? '').not.toMatch(/修订采集|取消采集|会话过期/);
  });

  it('keeps failed task details out of the workstation dashboard', async () => {
    renderWorkstation();

    const table = await screen.findByRole('table');
    const failedRow = within(table).getByText('task-failed').closest('tr') as HTMLElement;

    expect(failedRow.textContent).not.toContain('图像处理模块未配置');
    expect(within(failedRow).getByText('查看原因')).toBeTruthy();
  });

  it('opens task management from the sidebar without a full page reload', async () => {
    const user = userEvent.setup();
    renderWorkstation();

    await user.click(await screen.findByRole('link', { name: /任务管理/ }));

    expect(await screen.findByRole('main', { name: '任务列表页' })).toBeTruthy();
    expect(window.location.pathname).toBe('/tasks');
  });

  it('renders workstation navigation and task actions as connected links', async () => {
    renderWorkstation();

    expect(await screen.findByText('系统已启动')).toBeTruthy();
    expect(screen.getByRole('link', { name: /任务管理/ }).getAttribute('href')).toBe('/tasks');
    expect(screen.getByRole('link', { name: '全部任务' }).getAttribute('href')).toBe('/tasks');
    expect(screen.getByRole('link', { name: '进入审核' }).getAttribute('href')).toBe('/tasks/task-ready/review');
    expect(screen.getByRole('link', { name: '导出' }).getAttribute('href')).toBe('/tasks/task-done/export');
  });

  it('creates an uploading task and shows task upload QR dialog', async () => {
    const user = userEvent.setup();
    server.use(mockSystemStatus(), mockTasks(taskFixtures), mockCreateTask());
    render(<App />);

    await screen.findByText('系统已启动');
    await user.click(screen.getByRole('button', { name: /新建任务/ }));

    const dialog = await screen.findByRole('dialog', { name: '任务上传二维码' });
    const qrImage = (await within(dialog).findByRole('img', { name: '任务上传二维码' })) as HTMLImageElement;
    expect(qrImage.src).toMatch(/^data:image\/svg\+xml/);
    expect(qrImage.dataset.qrValue).toBe('http://127.0.0.1:8081/mobile/upload/task_001?token=token_001');
    expect(within(dialog).getByText('任务已创建')).toBeTruthy();
    expect(within(dialog).getByText('task_001')).toBeTruthy();
    expect(within(dialog).getByText('http://127.0.0.1:8081/mobile/upload/task_001?token=token_001')).toBeTruthy();
    expect(within(dialog).getByText(/已上传 0 张图片/)).toBeTruthy();
    expect(dialog.querySelector('.qr-dialog__illustration')).toBeNull();
    expect(document.body.textContent ?? '').not.toMatch(/会话过期|修订采集|取消采集/);
  });

  it('lets the QR dialog choose a LAN address or manual mobile link', async () => {
    const user = userEvent.setup();
    server.use(mockSystemStatus(), mockTasks(taskFixtures), mockCreateTask());
    render(<App />);

    await screen.findByText('系统已启动');
    await user.click(screen.getByRole('button', { name: /新建任务/ }));

    const dialog = await screen.findByRole('dialog', { name: '任务上传二维码' });
    await within(dialog).findByRole('img', { name: '任务上传二维码' });
    await user.click(within(dialog).getByRole('button', { name: '手机无法连接？' }));

    expect((within(dialog).getByLabelText('手机访问链接') as HTMLInputElement).value).toBe(
      'http://127.0.0.1:8081/mobile/upload/task_001?token=token_001'
    );

    await user.click(within(dialog).getByRole('button', { name: '192.168.1.5:8081' }));
    const lanQrImage = (await within(dialog).findByRole('img', { name: '任务上传二维码' })) as HTMLImageElement;
    expect(lanQrImage.dataset.qrValue).toBe(
      'http://192.168.1.5:8081/mobile/upload/task_001?token=token_001'
    );

    const input = within(dialog).getByLabelText('手机访问链接');
    await user.clear(input);
    await user.type(input, 'http://10.0.0.8:8081/mobile/upload/task_001?token=manual');
    await user.click(within(dialog).getByRole('button', { name: '更新二维码' }));

    const manualQrImage = (await within(dialog).findByRole('img', { name: '任务上传二维码' })) as HTMLImageElement;
    expect(manualQrImage.dataset.qrValue).toBe('http://10.0.0.8:8081/mobile/upload/task_001?token=manual');
  });

  it('shows task creation errors without keeping an old QR dialog', async () => {
    const user = userEvent.setup();
    server.use(mockSystemStatus(), mockTasks([]), mockCreateTaskError());
    render(<App />);

    await user.click(await screen.findByRole('button', { name: /新建任务/ }));

    expect(await screen.findByText('创建任务失败，请重试')).toBeTruthy();
    expect(screen.queryByRole('dialog', { name: '任务上传二维码' })).toBeNull();
  });
});
