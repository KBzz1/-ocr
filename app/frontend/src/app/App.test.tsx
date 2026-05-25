import { act, render, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { http, HttpResponse } from 'msw';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

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

function mockReadyTaskReview() {
  return http.get('*/api/tasks/task-ready/review', () =>
    HttpResponse.json({
      success: true,
      data: {
        task_id: 'task-ready',
        status: 'review',
        review_result: {
          ocr_text: '姓名：张三',
          pages: [{ page_id: 'page_001', page_no: 1, parsed_text: '姓名：张三' }],
          fields: [{ field_key: 'patient_name', label: '姓名', value: '张三', status: 'unreviewed' }]
        }
      }
    })
  );
}

describe('Workstation data integration', () => {
  beforeEach(() => {
    window.history.pushState({}, '', '/');
  });

  afterEach(() => {
    vi.useRealTimers();
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

  it('silently refreshes dashboard task statuses', async () => {
    vi.useFakeTimers({ shouldAdvanceTime: true });
    Object.defineProperty(document, 'visibilityState', {
      configurable: true,
      value: 'visible'
    });
    const refreshedTasks = taskFixtures.map((task) =>
      task.task_id === 'task-processing'
        ? { ...task, status: 'review' as const }
        : task
    );
    let requestCount = 0;
    server.use(
      mockSystemStatus(),
      http.get('*/api/tasks', () => {
        requestCount += 1;
        return HttpResponse.json({
          success: true,
          data: { tasks: requestCount === 1 ? taskFixtures : refreshedTasks }
        });
      })
    );
    render(<App />);

    const table = await screen.findByRole('table');
    const processingRow = within(table).getByText('task-processing').closest('tr') as HTMLElement;
    expect(processingRow.textContent).toContain('OCR 文档解析');
    expect(processingRow.textContent).not.toContain('处理中');

    await act(async () => {
      vi.advanceTimersByTime(5000);
    });

    await waitFor(() => expect(processingRow.textContent).toContain('待审核'));
  });

  it('opens task management from the sidebar without a full page reload', async () => {
    const user = userEvent.setup();
    renderWorkstation();

    await user.click(await screen.findByRole('link', { name: /任务管理/ }));

    expect(await screen.findByRole('main', { name: '任务列表页' })).toBeTruthy();
    expect(window.location.pathname).toBe('/tasks');
  });

  it('opens the review workspace from the global navigation', async () => {
    const user = userEvent.setup();
    server.use(mockReadyTaskReview());
    renderWorkstation();

    await user.click(await screen.findByRole('link', { name: /人工审核/ }));

    expect(await screen.findByRole('main', { name: '人工审核页' })).toBeTruthy();
    expect(screen.queryByRole('main', { name: '任务列表页' })).toBeNull();
    expect(window.location.pathname).toBe('/review');
    expect(screen.getAllByText('任务 task-ready').length).toBeGreaterThan(0);
    expect(screen.getByLabelText('patient_name')).toBeTruthy();
  });

  it('shows a local demo review sample when no real task is waiting for review', async () => {
    const user = userEvent.setup();
    server.use(mockSystemStatus(), mockTasks([]));
    render(<App />);

    await user.click(await screen.findByRole('link', { name: /人工审核/ }));

    expect(await screen.findByRole('main', { name: '人工审核页' })).toBeTruthy();
    expect(screen.queryByText('暂无待审核任务')).toBeNull();
    expect(screen.getByText('演示样本')).toBeTruthy();
    expect(screen.getAllByText('任务 task-demo-review').length).toBeGreaterThan(0);
    expect(screen.getByLabelText('patient_name')).toBeTruthy();
    expect(screen.getByLabelText('chief_complaint')).toBeTruthy();
    await user.click(screen.getByRole('button', { name: '显示 OCR' }));
    expect(screen.getAllByText(/模拟 OCR 文本/).length).toBeGreaterThan(0);

    await user.type(screen.getByLabelText('patient_name'), '修改');
    await user.click(screen.getByRole('button', { name: '保存修改' }));
    expect((await screen.findAllByText('已保存')).length).toBeGreaterThan(0);

    await user.click(screen.getByRole('button', { name: '确认完成' }));
    expect((await screen.findAllByText('已完成')).length).toBeGreaterThan(0);
  });

  it('renders workstation navigation and task actions as connected links', async () => {
    renderWorkstation();

    expect(await screen.findByText('系统已启动')).toBeTruthy();
    expect(screen.getByRole('link', { name: /任务管理/ }).getAttribute('href')).toBe('/tasks');
    expect(screen.getByRole('link', { name: /人工审核/ }).getAttribute('href')).toBe('/review');
    expect(screen.getByRole('link', { name: '全部任务' }).getAttribute('href')).toBe('/tasks');
    expect(screen.getByRole('link', { name: '进入审核' }).getAttribute('href')).toBe('/tasks/task-ready/review');
    expect(screen.getByRole('link', { name: '导出' }).getAttribute('href')).toBe('/tasks/task-done/export');
  });

  it('places partner logos in the sidebar brand area without the old text brand', async () => {
    renderWorkstation();

    await screen.findByText('系统已启动');

    const sidebar = screen.getByLabelText('工作站导航');
    const partnerLogos = within(sidebar).getByLabelText('合作单位');
    expect(within(partnerLogos).getByRole('img', { name: '重庆大学' })).toBeTruthy();
    expect(within(partnerLogos).getByRole('img', { name: '新桥医院' })).toBeTruthy();
    expect(sidebar.textContent ?? '').not.toContain('病历采集工作站');
    expect(sidebar.textContent ?? '').not.toContain('本地化部署版');
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
    expect(within(dialog).getByRole('button', { name: '重新生成二维码' })).toBeTruthy();
    expect(within(dialog).queryByText('任务已创建')).toBeNull();
    expect(within(dialog).queryByText('task_001')).toBeNull();
    expect(within(dialog).queryByText('http://127.0.0.1:8081/mobile/upload/task_001?token=token_001')).toBeNull();
    expect(within(dialog).queryByText(/已上传 0 张图片/)).toBeNull();
    expect(within(dialog).queryByRole('button', { name: '关闭' })).toBeNull();
    expect(dialog.querySelector('.qr-dialog__illustration')).toBeNull();
    expect(document.body.textContent ?? '').not.toMatch(/会话过期|修订采集|取消采集/);
  });

  it('regenerates the visible QR code without creating another task or refreshing the dashboard', async () => {
    const user = userEvent.setup();
    let createCount = 0;
    server.use(
      mockSystemStatus(),
      mockTasks(taskFixtures),
      http.post('*/api/tasks', () => {
        createCount += 1;
        return HttpResponse.json({
          success: true,
          data: {
            task_id: 'task_001',
            status: 'uploading',
            upload_token: 'token_001',
            mobile_upload_url: 'http://127.0.0.1:8081/mobile/upload/task_001?token=token_001'
          }
        });
      })
    );
    render(<App />);

    await screen.findByText('系统已启动');
    await user.click(screen.getByRole('button', { name: /新建任务/ }));

    const dialog = await screen.findByRole('dialog', { name: '任务上传二维码' });
    const firstQrImage = (await within(dialog).findByRole('img', { name: '任务上传二维码' })) as HTMLImageElement;
    const firstQrValue = firstQrImage.dataset.qrValue;
    await user.click(within(dialog).getByRole('button', { name: '重新生成二维码' }));
    expect(within(dialog).getByRole('button', { name: '重新生成二维码' })).toBeTruthy();
    const regeneratedQrImage = (await within(dialog).findByRole('img', { name: '任务上传二维码' })) as HTMLImageElement;

    expect(createCount).toBe(1);
    expect(screen.getByRole('dialog', { name: '任务上传二维码' })).toBeTruthy();
    expect(firstQrValue).toBe('http://127.0.0.1:8081/mobile/upload/task_001?token=token_001');
    expect(regeneratedQrImage.dataset.qrValue).toBe(
      'http://127.0.0.1:8081/mobile/upload/task_001?token=token_001&qr_refresh=1'
    );
  });

  it('shows only copy link guidance when the QR dialog help is opened', async () => {
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
    expect(within(dialog).getByRole('button', { name: '复制链接' })).toBeTruthy();
    expect(within(dialog).getByText('请确认手机与电脑连接同一局域网或电脑热点，再在手机浏览器打开此链接。')).toBeTruthy();
    expect(within(dialog).queryByRole('button', { name: '192.168.1.5:8081' })).toBeNull();
    expect(within(dialog).queryByRole('button', { name: '更新二维码' })).toBeNull();
    expect(within(dialog).queryByRole('button', { name: '关闭' })).toBeNull();
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
