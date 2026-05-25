import { act, render, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { http, HttpResponse } from 'msw';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import {
  mockRetryTaskProcessing,
  mockTasks,
  taskFixtures
} from '../../../tests/fixtures/tasks';
import { server } from '../../../tests/setupTests';
import { TasksPage } from './TasksPage';

function renderTaskList() {
  server.use(mockTasks());
  return render(<TasksPage />);
}

describe('MVP task list and retry', () => {
  beforeEach(() => {
    window.history.pushState({}, '', '/tasks');
  });

  afterEach(() => {
    vi.useRealTimers();
  });

  it('renders five MVP filters and task operations', async () => {
    renderTaskList();

    expect(await screen.findByRole('button', { name: '全部' })).toBeTruthy();
    expect(screen.getByRole('button', { name: '上传中' })).toBeTruthy();
    expect(screen.getByRole('button', { name: '处理中' })).toBeTruthy();
    expect(screen.getByRole('button', { name: '待审核' })).toBeTruthy();
    expect(screen.getByRole('button', { name: '已完成' })).toBeTruthy();
    expect(screen.getByRole('button', { name: '失败' })).toBeTruthy();
    expect(screen.queryByText('修订采集')).toBeNull();
    expect(screen.queryByText('取消会话')).toBeNull();
    expect(screen.queryByText('已导出')).toBeNull();
  });

  it('shows task identity, timestamps, page counts, and shared status labels', async () => {
    renderTaskList();

    const table = await screen.findByRole('table', { name: '任务列表' });
    const readyRow = within(table).getByText('task-ready').closest('tr');
    const failedRow = within(table).getByText('task-failed').closest('tr');

    expect(readyRow).not.toBeNull();
    expect((readyRow as HTMLElement).textContent).toContain('2026/05/19 09:30');
    expect((readyRow as HTMLElement).textContent).toContain('3 页');
    expect((readyRow as HTMLElement).textContent).toContain('待审核');
    expect((readyRow as HTMLElement).textContent).toContain('未审核');
    expect((readyRow as HTMLElement).textContent).toContain('进入审核');
    expect((readyRow as HTMLElement).textContent).toContain('导出');

    expect(failedRow).not.toBeNull();
    expect((failedRow as HTMLElement).textContent).toContain('失败');
    expect((failedRow as HTMLElement).textContent).toContain('图像处理模块未配置');
  });

  it('filters by five MVP statuses', async () => {
    const user = userEvent.setup();
    renderTaskList();

    await screen.findByRole('table', { name: '任务列表' });
    await user.click(screen.getByRole('button', { name: '待审核' }));

    expect(screen.getByText('task-ready')).not.toBeNull();
    expect(screen.queryByText('task-failed')).toBeNull();
    expect(screen.queryByText('task-processing')).toBeNull();

    await user.click(screen.getByRole('button', { name: '失败' }));

    expect(screen.getByText('task-failed')).not.toBeNull();
    expect(screen.queryByText('task-ready')).toBeNull();
    expect(screen.queryByText('task-processing')).toBeNull();
  });

  it('uses the status query parameter when opening failed task reasons', async () => {
    const user = userEvent.setup();
    window.history.pushState({}, '', '/tasks?status=failed');
    server.use(mockTasks());
    render(<TasksPage />);

    await screen.findByRole('table', { name: '任务列表' });

    expect(screen.getByRole('button', { name: '失败' }).getAttribute('aria-pressed')).toBe('true');
    expect(screen.getByText('task-failed')).not.toBeNull();
    expect(screen.getAllByText('图像处理模块未配置').length).toBeGreaterThan(0);
    expect(screen.queryByText('task-ready')).toBeNull();
    expect(screen.queryByText('task-processing')).toBeNull();

    await user.click(screen.getByRole('button', { name: '全部' }));

    expect(screen.getByRole('button', { name: '全部' }).getAttribute('aria-pressed')).toBe('true');
    expect(window.location.pathname + window.location.search).toBe('/tasks');
    expect(screen.getByText('task-ready')).not.toBeNull();
    expect(screen.getByText('task-processing')).not.toBeNull();
  });

  it('refreshes task data and shows backend status changes', async () => {
    const user = userEvent.setup();
    const refreshedTasks = taskFixtures.map((task) =>
      task.task_id === 'task-processing'
        ? { ...task, status: 'review' as const }
        : task
    );
    let requestCount = 0;

    server.use(
      http.get('*/api/tasks', () => {
        requestCount += 1;
        return HttpResponse.json({
          success: true,
          data: { tasks: requestCount === 1 ? taskFixtures : refreshedTasks }
        });
      })
    );

    render(<TasksPage />);

    const table = await screen.findByRole('table', { name: '任务列表' });
    expect((within(table).getByText('task-processing').closest('tr') as HTMLElement).textContent).toContain(
      '处理中'
    );

    await user.click(screen.getByRole('button', { name: '刷新' }));

    await waitFor(() =>
      expect((within(table).getByText('task-processing').closest('tr') as HTMLElement).textContent).toContain(
        '待审核'
      )
    );
  });

  it('shows processing stage progress for running tasks', async () => {
    renderTaskList();

    const table = await screen.findByRole('table', { name: '任务列表' });
    const processingRow = within(table).getByText('task-processing').closest('tr') as HTMLElement;
    const statusCell = processingRow.children[3] as HTMLElement;
    const actionsCell = processingRow.children[6] as HTMLElement;

    expect(statusCell.textContent).toContain('OCR 文档解析');
    expect(within(statusCell).getByRole('progressbar', { name: '处理进度' }).getAttribute('aria-valuenow')).toBe('55');
    expect(within(actionsCell).queryByRole('progressbar', { name: '处理进度' })).toBeNull();
  });

  it('opens the upload QR dialog for an uploading task', async () => {
    const user = userEvent.setup();
    server.use(
      mockTasks([
        {
          task_id: 'task_046',
          status: 'uploading',
          created_at: '2026-05-20T20:55:00+08:00',
          page_count: 1,
          upload_token: 'token_046',
          mobile_upload_url: 'http://192.168.1.5:8081/mobile/upload/task_046?token=token_046',
          review_summary: { status: null, confirmed_count: 0, total_count: 0 },
          export_summary: { formats: [] },
          error_code: null,
          error_message: null
        }
      ])
    );
    render(<TasksPage />);

    const table = await screen.findByRole('table', { name: '任务列表' });
    const row = within(table).getByText('task_046').closest('tr') as HTMLElement;
    await user.click(within(row).getByRole('button', { name: '查看二维码' }));

    const dialog = await screen.findByRole('dialog', { name: '任务上传二维码' });
    const qrImage = (await within(dialog).findByRole('img', { name: '任务上传二维码' })) as HTMLImageElement;
    expect(qrImage.dataset.qrValue).toBe('http://192.168.1.5:8081/mobile/upload/task_046?token=token_046');
  });

  it('silently polls task data without showing a refresh state', async () => {
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
      http.get('*/api/tasks', () => {
        requestCount += 1;
        return HttpResponse.json({
          success: true,
          data: { tasks: requestCount === 1 ? taskFixtures : refreshedTasks }
        });
      })
    );

    render(<TasksPage />);

    const table = await screen.findByRole('table', { name: '任务列表' });
    const processingRow = within(table).getByText('task-processing').closest('tr') as HTMLElement;
    expect(processingRow.textContent).toContain('处理中');

    await act(async () => {
      vi.advanceTimersByTime(5000);
    });

    await waitFor(() => expect(processingRow.textContent).toContain('待审核'));
    expect(screen.getByRole('button', { name: '刷新' })).toBeTruthy();
  });

  it('retries failed tasks, updates the row to processing, and never offers legacy actions', async () => {
    const user = userEvent.setup();
    const retrySpy = vi.fn();

    server.use(
      mockTasks(),
      mockRetryTaskProcessing('task-failed', () => {
        retrySpy();
        return { task_id: 'task-failed', status: 'processing' };
      })
    );
    render(<TasksPage />);

    const table = await screen.findByRole('table', { name: '任务列表' });
    const failedRow = within(table).getByText('task-failed').closest('tr') as HTMLElement;

    expect(within(failedRow).queryByRole('link', { name: '进入审核' })).toBeNull();
    expect(document.body.textContent ?? '').not.toContain('修订采集');
    expect(document.body.textContent ?? '').not.toContain('取消会话');

    await user.click(within(failedRow).getByRole('button', { name: '重新处理' }));

    await waitFor(() => expect(retrySpy).toHaveBeenCalledTimes(1));
    await waitFor(() => expect(failedRow.textContent).toContain('处理中'));
  });
});
