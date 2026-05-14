import { render, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { http, HttpResponse } from 'msw';
import { describe, expect, it, vi } from 'vitest';

import {
  mockRetryTaskProcessing,
  mockTasks,
  taskFixtures
} from '../../../tests/fixtures/tasks';
import { server } from '../../../tests/setupTests';
import { TasksPlaceholder } from './TasksPlaceholder';

function renderTaskList() {
  server.use(mockTasks());
  return render(<TasksPlaceholder />);
}

describe('FE-03 task list and retry', () => {
  it('shows task identity, timestamps, page counts, and shared status labels', async () => {
    renderTaskList();

    const table = await screen.findByRole('table', { name: '任务列表' });
    const readyRow = within(table).getByText('task-ready').closest('tr');
    const failedRow = within(table).getByText('task-failed').closest('tr');

    expect(readyRow).not.toBeNull();
    expect((readyRow as HTMLElement).textContent).toContain('2026/05/13 09:30');
    expect((readyRow as HTMLElement).textContent).toContain('3 页');
    expect((readyRow as HTMLElement).textContent).toContain('待审核');
    expect((readyRow as HTMLElement).textContent).toContain('未审核');
    expect((readyRow as HTMLElement).textContent).toContain('未导出');

    expect(failedRow).not.toBeNull();
    expect((failedRow as HTMLElement).textContent).toContain('处理失败');
    expect((failedRow as HTMLElement).textContent).toContain('图像处理模块未配置');
  });

  it('filters by review-ready and failed status without inferring new statuses', async () => {
    const user = userEvent.setup();
    renderTaskList();

    await screen.findByRole('table', { name: '任务列表' });
    await user.click(screen.getByRole('button', { name: '待审核' }));

    expect(screen.getByText('task-ready')).not.toBeNull();
    expect(screen.queryByText('task-failed')).toBeNull();
    expect(screen.queryByText('task-processing')).toBeNull();

    await user.click(screen.getByRole('button', { name: '处理失败' }));

    expect(screen.getByText('task-failed')).not.toBeNull();
    expect(screen.queryByText('task-ready')).toBeNull();
    expect(screen.queryByText('task-processing')).toBeNull();
  });

  it('refreshes task data and shows backend status changes', async () => {
    const user = userEvent.setup();
    const refreshedTasks = taskFixtures.map((task) =>
      task.task_id === 'task-processing'
        ? { ...task, status: 'ready_for_review' as const }
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

    render(<TasksPlaceholder />);

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

  it('retries failed tasks, updates the row to processing, and never offers normal review', async () => {
    const user = userEvent.setup();
    const retrySpy = vi.fn();

    server.use(
      mockTasks(),
      mockRetryTaskProcessing('task-failed', () => {
        retrySpy();
        return { task_id: 'task-failed', status: 'processing' };
      })
    );
    render(<TasksPlaceholder />);

    const table = await screen.findByRole('table', { name: '任务列表' });
    const failedRow = within(table).getByText('task-failed').closest('tr') as HTMLElement;

    expect(within(failedRow).queryByRole('link', { name: '开始审核' })).toBeNull();
    expect(document.body.textContent ?? '').not.toContain('查看日志');
    expect(document.body.textContent ?? '').not.toContain('人工降级');

    await user.click(within(failedRow).getByRole('button', { name: '重新处理' }));

    await waitFor(() => expect(retrySpy).toHaveBeenCalledTimes(1));
    await waitFor(() => expect(failedRow.textContent).toContain('处理中'));
  });
});
