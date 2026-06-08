import { act, render, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { http, HttpResponse } from 'msw';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import {
  mockCancelTaskProcessing,
  mockDeleteTask,
  mockRetryTaskProcessing,
  mockTasks,
  taskFixtures
} from '../../../tests/fixtures/tasks';
import type { TaskSummary } from '../../api/tasks';
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
    expect(screen.queryByRole('button', { name: '处理中' })).toBeNull();
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
    const readyRow = within(table).getByText('2').closest('tr');
    const failedRow = within(table).getByText('4').closest('tr');

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

    expect(screen.getByText('2')).not.toBeNull();
    expect(screen.queryByText('4')).toBeNull();
    expect(screen.queryByText('3')).toBeNull();

    await user.click(screen.getByRole('button', { name: '失败' }));

    expect(screen.getByText('4')).not.toBeNull();
    expect(screen.queryByText('2')).toBeNull();
    expect(screen.queryByText('3')).toBeNull();
  });

  it('uses the status query parameter when opening failed task reasons', async () => {
    const user = userEvent.setup();
    window.history.pushState({}, '', '/tasks?status=failed');
    server.use(mockTasks());
    render(<TasksPage />);

    await screen.findByRole('table', { name: '任务列表' });

    expect(screen.getByRole('button', { name: '失败' }).getAttribute('aria-pressed')).toBe('true');
    expect(screen.getByText('4')).not.toBeNull();
    expect(screen.getAllByText('图像处理模块未配置').length).toBeGreaterThan(0);
    expect(screen.queryByText('2')).toBeNull();
    expect(screen.queryByText('3')).toBeNull();

    await user.click(screen.getByRole('button', { name: '全部' }));

    expect(screen.getByRole('button', { name: '全部' }).getAttribute('aria-pressed')).toBe('true');
    expect(window.location.pathname + window.location.search).toBe('/tasks');
    expect(screen.getByText('2')).not.toBeNull();
    expect(screen.getByText('3')).not.toBeNull();
  });

  it('refreshes task data and shows backend status changes', async () => {
    const user = userEvent.setup();
    const refreshedTasks = taskFixtures.map((task) =>
      task.task_id === '3'
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
    expect(within(within(table).getByText('3').closest('tr') as HTMLElement).getByRole('button', { name: '取消处理' })).toBeTruthy();

    await user.click(screen.getByRole('button', { name: '刷新' }));

    await waitFor(() =>
      expect((within(table).getByText('3').closest('tr') as HTMLElement).textContent).toContain(
        '待审核'
      )
    );
  });

  it('shows processing stage progress for running tasks', async () => {
    renderTaskList();

    const table = await screen.findByRole('table', { name: '任务列表' });
    const processingRow = within(table).getByText('3').closest('tr') as HTMLElement;
    const statusCell = processingRow.querySelector('td.task-status-cell-td') as HTMLElement;
    const actionsCell = processingRow.querySelector('td:last-child') as HTMLElement;

    expect(statusCell.textContent).not.toContain('处理中');
    expect(statusCell.textContent).toContain('OCR 文档解析');
    expect(within(statusCell).getByRole('progressbar', { name: '处理进度' }).getAttribute('aria-valuenow')).toBe('55');
    expect(within(actionsCell).queryByRole('progressbar', { name: '处理进度' })).toBeNull();
    expect(within(actionsCell).getByRole('button', { name: '取消处理' })).toBeTruthy();
  });

  it('cancels processing tasks and updates the row to failed', async () => {
    const user = userEvent.setup();
    const cancelSpy = vi.fn();

    server.use(
      mockTasks(),
      mockCancelTaskProcessing('3', () => {
        cancelSpy();
        return {
          task_id: '3',
          status: 'failed',
          error_code: 'TASK_PROCESSING_CANCELLED',
          error_message: '用户取消处理'
        };
      })
    );
    render(<TasksPage />);

    const table = await screen.findByRole('table', { name: '任务列表' });
    const processingRow = within(table).getByText('3').closest('tr') as HTMLElement;

    await user.click(within(processingRow).getByRole('button', { name: '取消处理' }));

    await waitFor(() => expect(cancelSpy).toHaveBeenCalledTimes(1));
    await waitFor(() => expect(processingRow.textContent).toContain('失败'));
    expect(processingRow.textContent).toContain('用户取消处理');
  });

  it('opens the upload QR dialog for an uploading task', async () => {
    const user = userEvent.setup();
    server.use(
      mockTasks([
        {
          task_id: '46',
          display_name: '46',
          status: 'uploading',
          created_at: '2026-05-20T20:55:00+08:00',
          page_count: 1,
          upload_token: 'token_046',
          mobile_upload_url: 'http://192.168.1.5:8081/mobile/upload/46?token=token_046',
          review_summary: { status: null, confirmed_count: 0, total_count: 0 },
          export_summary: { formats: [] },
          error_code: null,
          error_message: null
        }
      ])
    );
    render(<TasksPage />);

    const table = await screen.findByRole('table', { name: '任务列表' });
    const row = within(table).getByText('46').closest('tr') as HTMLElement;
    await user.click(within(row).getByRole('button', { name: '查看二维码' }));

    const dialog = await screen.findByRole('dialog', { name: '任务上传二维码' });
    const qrImage = (await within(dialog).findByRole('img', { name: '任务上传二维码' })) as HTMLImageElement;
    expect(qrImage.dataset.qrValue).toBe('http://192.168.1.5:8081/mobile/upload/46?token=token_046');
  });

  it('silently polls task data without showing a refresh state', async () => {
    vi.useFakeTimers({ shouldAdvanceTime: true });
    Object.defineProperty(document, 'visibilityState', {
      configurable: true,
      value: 'visible'
    });
    const refreshedTasks = taskFixtures.map((task) =>
      task.task_id === '3'
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
    const processingRow = within(table).getByText('3').closest('tr') as HTMLElement;
    expect(within(processingRow).getByRole('button', { name: '取消处理' })).toBeTruthy();

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
      mockRetryTaskProcessing('4', () => {
        retrySpy();
        return { task_id: '4', status: 'processing' };
      })
    );
    render(<TasksPage />);

    const table = await screen.findByRole('table', { name: '任务列表' });
    const failedRow = within(table).getByText('4').closest('tr') as HTMLElement;

    expect(within(failedRow).queryByRole('link', { name: '进入审核' })).toBeNull();
    expect(document.body.textContent ?? '').not.toContain('修订采集');
    expect(document.body.textContent ?? '').not.toContain('取消会话');

    await user.click(within(failedRow).getByRole('button', { name: '重新处理' }));

    await waitFor(() => expect(retrySpy).toHaveBeenCalledTimes(1));
    await waitFor(() => expect(within(failedRow).getByRole('button', { name: '取消处理' })).toBeTruthy());
  });
});

describe('Delete task with confirmation dialog', () => {
  beforeEach(() => {
    window.history.pushState({}, '', '/tasks');
  });

  it('shows delete button for non-processing tasks and not for processing tasks', async () => {
    renderTaskList();

    const table = await screen.findByRole('table', { name: '任务列表' });
    const reviewRow = within(table).getByText('2').closest('tr') as HTMLElement;
    const processingRow = within(table).getByText('3').closest('tr') as HTMLElement;
    const failedRow = within(table).getByText('4').closest('tr') as HTMLElement;
    const doneRow = within(table).getByText('5').closest('tr') as HTMLElement;

    expect(within(reviewRow).getByRole('button', { name: '删除' })).toBeTruthy();
    expect(within(processingRow).queryByRole('button', { name: '删除' })).toBeNull();
    expect(within(failedRow).getByRole('button', { name: '删除' })).toBeTruthy();
    expect(within(doneRow).getByRole('button', { name: '删除' })).toBeTruthy();
  });

  it('opens confirmation dialog when delete button is clicked', async () => {
    const user = userEvent.setup();
    renderTaskList();

    const table = await screen.findByRole('table', { name: '任务列表' });
    const failedRow = within(table).getByText('4').closest('tr') as HTMLElement;
    await user.click(within(failedRow).getByRole('button', { name: '删除' }));

    expect(screen.getByRole('alertdialog', { name: '确认删除任务' })).toBeTruthy();
    expect(screen.getByText('4', { selector: 'strong' })).toBeTruthy();
    expect(screen.getByRole('button', { name: '确认删除' })).toBeTruthy();
    expect(screen.getByRole('button', { name: '取消' })).toBeTruthy();
  });

  it('closes confirmation dialog when cancel is clicked', async () => {
    const user = userEvent.setup();
    renderTaskList();

    const table = await screen.findByRole('table', { name: '任务列表' });
    const failedRow = within(table).getByText('4').closest('tr') as HTMLElement;
    await user.click(within(failedRow).getByRole('button', { name: '删除' }));

    expect(screen.getByRole('alertdialog')).toBeTruthy();

    await user.click(screen.getByRole('button', { name: '取消' }));

    await waitFor(() => expect(screen.queryByRole('alertdialog')).toBeNull());
  });

  it('deletes the task and removes it from the list after confirmation', async () => {
    const user = userEvent.setup();
    server.use(mockTasks(), mockDeleteTask('4'));
    render(<TasksPage />);

    const table = await screen.findByRole('table', { name: '任务列表' });
    const failedRow = within(table).getByText('4').closest('tr') as HTMLElement;
    await user.click(within(failedRow).getByRole('button', { name: '删除' }));
    await user.click(screen.getByRole('button', { name: '确认删除' }));

    await waitFor(() => expect(screen.queryByText('4')).toBeNull());
    expect(screen.queryByRole('alertdialog')).toBeNull();
  });

  it('shows an error when delete confirmation fails', async () => {
    const user = userEvent.setup();
    server.use(
      mockTasks(),
      http.delete('*/api/tasks/4', () =>
        HttpResponse.json(
          { error: { code: 'TASK_DELETE_FAILED', message: '删除任务失败', details: {} } },
          { status: 500 }
        )
      )
    );
    render(<TasksPage />);

    const table = await screen.findByRole('table', { name: '任务列表' });
    const failedRow = within(table).getByText('4').closest('tr') as HTMLElement;
    await user.click(within(failedRow).getByRole('button', { name: '删除' }));
    await user.click(screen.getByRole('button', { name: '确认删除' }));

    expect(await screen.findByText('删除任务失败')).toBeTruthy();
    expect(screen.getByText('4')).toBeTruthy();
  });

  it('closes confirmation dialog when backdrop is clicked', async () => {
    const user = userEvent.setup();
    renderTaskList();

    const table = await screen.findByRole('table', { name: '任务列表' });
    const failedRow = within(table).getByText('4').closest('tr') as HTMLElement;
    await user.click(within(failedRow).getByRole('button', { name: '删除' }));

    expect(screen.getByRole('alertdialog')).toBeTruthy();

    await user.click(screen.getByRole('presentation'));

    await waitFor(() => expect(screen.queryByRole('alertdialog')).toBeNull());
  });
});

describe('Task list patient/record binding and rebind', () => {
  beforeEach(() => {
    window.history.pushState({}, '', '/tasks');
  });

  it('shows a single 患者与记录 column with patient, record type, and record date', async () => {
    renderTaskList();

    const table = await screen.findByRole('table', { name: '任务列表' });
    const headerCells = within(table).getAllByRole('columnheader').map((cell) => cell.textContent?.trim() ?? '');
    expect(headerCells).toContain('患者与记录');

    const reviewRow = within(table).getByText('2').closest('tr') as HTMLElement;
    // 患者姓名 + 患者编号在同一单元格
    expect(within(reviewRow).getByText('测试用例')).toBeTruthy();
    expect(within(reviewRow).getByText('P-A1B2C3D4')).toBeTruthy();
    // 记录类型
    expect(within(reviewRow).getByText('入院记录')).toBeTruthy();
    // 记录日期(无时间时只显示日期)
    expect(within(reviewRow).getByText('2026-06-06')).toBeTruthy();
  });

  it('shows the record time after the date when present', async () => {
    renderTaskList();

    const table = await screen.findByRole('table', { name: '任务列表' });
    const doneRow = within(table).getByText('5').closest('tr') as HTMLElement;
    // 任务 5 有具体时间,单元格内应同时出现日期 + 时间
    expect(within(doneRow).getByText('2026-06-03 10:15')).toBeTruthy();
  });

  it('marks tasks whose patient is deleted with a 患者已删除 badge in the same cell', async () => {
    renderTaskList();

    const table = await screen.findByRole('table', { name: '任务列表' });
    const failedRow = within(table).getByText('4').closest('tr') as HTMLElement;
    expect(within(failedRow).getByText('患者已删除')).toBeTruthy();
    // 删除任务 4 之外,其余行不应出现"患者已删除"
    const reviewRow = within(table).getByText('2').closest('tr') as HTMLElement;
    expect(within(reviewRow).queryByText('患者已删除')).toBeNull();
  });

  it('opens a rebind dialog with a search box and 选择/新建 actions', async () => {
    const user = userEvent.setup();
    server.use(
      mockTasks(),
      http.get('*/api/patients*', () =>
        HttpResponse.json({
          success: true,
          data: {
            patients: [
              {
                patient_id: 'P-AABBCCDD',
                name: '测试用例',
                created_at: '2026-06-07T10:00:00+08:00',
                updated_at: '2026-06-07T10:00:00+08:00',
                task_count: 2,
                latest_record_at: '2026-06-07'
              }
            ]
          }
        })
      )
    );
    render(<TasksPage />);

    const table = await screen.findByRole('table', { name: '任务列表' });
    const reviewRow = within(table).getByText('2').closest('tr') as HTMLElement;
    await user.click(within(reviewRow).getByRole('button', { name: '改绑患者' }));

    const dialog = await screen.findByRole('dialog', { name: '改绑患者' });
    expect(within(dialog).getByLabelText('患者姓名')).toBeTruthy();
    expect(within(dialog).getByRole('button', { name: '搜索' })).toBeTruthy();
    expect(within(dialog).getByRole('button', { name: '仍然新建' })).toBeTruthy();
    expect(within(dialog).queryByLabelText('搜索患者')).toBeNull();
    expect(within(dialog).queryByLabelText('新患者姓名')).toBeNull();
  });

  it('rebinds the task to an existing patient via PATCH /api/tasks/{id}/metadata', async () => {
    const user = userEvent.setup();
    const patchSpy = vi.fn();
    server.use(
      mockTasks(),
      http.get('*/api/patients*', () =>
        HttpResponse.json({
          success: true,
          data: {
            patients: [
              {
                patient_id: 'P-AABBCCDD',
                name: '新患者',
                created_at: '2026-06-07T10:00:00+08:00',
                updated_at: '2026-06-07T10:00:00+08:00',
                task_count: 1,
                latest_record_at: '2026-06-06'
              }
            ]
          }
        })
      ),
      http.patch('*/api/tasks/2/metadata', async ({ request }) => {
        const body = (await request.json()) as Record<string, unknown>;
        patchSpy(body);
        return HttpResponse.json({
          success: true,
          data: {
            task_id: '2',
            display_name: '2',
            status: 'review',
            created_at: '2026-05-19T09:30:00+08:00',
            page_count: 3,
            patient: {
              patient_id: 'P-AABBCCDD',
              name: '新患者',
              deleted: false
            },
            document_type: 'copd_admission_record',
            document_type_label: '入院记录',
            record_date: '2026-06-06',
            record_time: null,
            review_summary: { status: 'unreviewed', confirmed_count: 0, total_count: 8 },
            export_summary: { formats: [] },
            error_code: null,
            error_message: null
          }
        });
      })
    );
    render(<TasksPage />);

    const table = await screen.findByRole('table', { name: '任务列表' });
    const reviewRow = within(table).getByText('2').closest('tr') as HTMLElement;
    await user.click(within(reviewRow).getByRole('button', { name: '改绑患者' }));

    const dialog = await screen.findByRole('dialog', { name: '改绑患者' });
    const searchInput = within(dialog).getByLabelText('患者姓名');
    await user.type(searchInput, '新患者');
    await user.click(within(dialog).getByRole('button', { name: '搜索' }));
    await user.click(within(dialog).getByRole('button', { name: /选择 P-AABBCCDD/ }));
    await user.click(within(dialog).getByRole('button', { name: '确认改绑' }));

    await waitFor(() => expect(patchSpy).toHaveBeenCalledWith({ patient_id: 'P-AABBCCDD' }));
    await waitFor(() => expect(within(reviewRow).getByText('新患者')).toBeTruthy());
    expect(within(reviewRow).getByText('P-AABBCCDD')).toBeTruthy();
  });

  it('creates a new patient in the rebind dialog and rebinds to it', async () => {
    const user = userEvent.setup();
    const createPatientSpy = vi.fn();
    const patchSpy = vi.fn();
    server.use(
      mockTasks(),
      http.get('*/api/patients*', () =>
        HttpResponse.json({ success: true, data: { patients: [] } })
      ),
      http.post('*/api/patients', async ({ request }) => {
        const body = (await request.json()) as Record<string, unknown>;
        createPatientSpy(body);
        return HttpResponse.json({
          success: true,
          data: {
            patient_id: 'P-FFEEDDCC',
            name: body.name,
            created_at: '2026-06-07T10:00:00+08:00',
            updated_at: '2026-06-07T10:00:00+08:00',
            deleted_at: null
          }
        });
      }),
      http.patch('*/api/tasks/2/metadata', async ({ request }) => {
        const body = (await request.json()) as Record<string, unknown>;
        patchSpy(body);
        return HttpResponse.json({
          success: true,
          data: {
            task_id: '2',
            display_name: '2',
            status: 'review',
            created_at: '2026-05-19T09:30:00+08:00',
            page_count: 3,
            patient: { patient_id: 'P-FFEEDDCC', name: '新档案', deleted: false },
            document_type: 'copd_admission_record',
            document_type_label: '入院记录',
            record_date: '2026-06-06',
            record_time: null,
            review_summary: { status: 'unreviewed', confirmed_count: 0, total_count: 8 },
            export_summary: { formats: [] },
            error_code: null,
            error_message: null
          }
        });
      })
    );
    render(<TasksPage />);

    const table = await screen.findByRole('table', { name: '任务列表' });
    const reviewRow = within(table).getByText('2').closest('tr') as HTMLElement;
    await user.click(within(reviewRow).getByRole('button', { name: '改绑患者' }));

    const dialog = await screen.findByRole('dialog', { name: '改绑患者' });
    const newNameInput = within(dialog).getByLabelText('患者姓名');
    await user.type(newNameInput, '新档案');
    await user.click(within(dialog).getByRole('button', { name: '仍然新建' }));
    // 新建后该患者已自动选择;直接点确认改绑
    await user.click(within(dialog).getByRole('button', { name: '确认改绑' }));

    await waitFor(() => expect(createPatientSpy).toHaveBeenCalledWith({ name: '新档案' }));
    await waitFor(() => expect(patchSpy).toHaveBeenCalledWith({ patient_id: 'P-FFEEDDCC' }));
  });

  it('disables rebind for processing tasks and explains the reason', async () => {
    renderTaskList();

    const table = await screen.findByRole('table', { name: '任务列表' });
    const processingRow = within(table).getByText('3').closest('tr') as HTMLElement;
    const button = within(processingRow).getByRole('button', { name: /改绑患者/ }) as HTMLButtonElement;
    expect(button.disabled).toBe(true);
    expect(button.getAttribute('title') ?? '').toMatch(/处理中/);
  });

  it('shows backend error message when rebind fails', async () => {
    const user = userEvent.setup();
    server.use(
      mockTasks(),
      http.get('*/api/patients*', () =>
        HttpResponse.json({
          success: true,
          data: {
            patients: [
              {
                patient_id: 'P-AAAABBBB',
                name: '已删除患者',
                created_at: '2026-06-07T10:00:00+08:00',
                updated_at: '2026-06-07T10:00:00+08:00',
                task_count: 0,
                latest_record_at: null,
                deleted_at: '2026-06-07T10:30:00+08:00'
              }
            ]
          }
        })
      ),
      http.patch('*/api/tasks/2/metadata', () =>
        HttpResponse.json(
          { error: { code: 'PATIENT_DELETED', message: '患者已删除,不能继续使用', details: {} } },
          { status: 409 }
        )
      )
    );
    render(<TasksPage />);

    const table = await screen.findByRole('table', { name: '任务列表' });
    const reviewRow = within(table).getByText('2').closest('tr') as HTMLElement;
    await user.click(within(reviewRow).getByRole('button', { name: '改绑患者' }));

    const dialog = await screen.findByRole('dialog', { name: '改绑患者' });
    const searchInput = within(dialog).getByLabelText('患者姓名');
    await user.type(searchInput, '已删除');
    await user.click(within(dialog).getByRole('button', { name: '搜索' }));
    await user.click(within(dialog).getByRole('button', { name: /选择 P-AAAABBBB/ }));
    await user.click(within(dialog).getByRole('button', { name: '确认改绑' }));

    expect(await within(dialog).findByText('患者已删除,不能继续使用')).toBeTruthy();
  });
});

describe('Batch export (FE-MVP-03-04)', () => {
  beforeEach(() => {
    window.history.pushState({}, '', '/tasks');
  });

  afterEach(() => {
    vi.useRealTimers();
  });

  it('shows checkboxes; review/done rows enable, others disable with explanation', async () => {
    // 在 taskFixtures 基础上把任务 1(uploading)的 page_count 调为 1,确保不被 shouldShowTask 过滤
    const customTasks: TaskSummary[] = taskFixtures.map((t) =>
      t.task_id === '1' ? { ...t, page_count: 1 } : t
    );
    server.use(http.get('*/api/tasks', () => HttpResponse.json({ success: true, data: { tasks: customTasks } })));
    render(<TasksPage />);

    const table = await screen.findByRole('table', { name: '任务列表' });
    const reviewRow = within(table).getByText('2').closest('tr') as HTMLElement;
    const doneRow = within(table).getByText('5').closest('tr') as HTMLElement;
    const uploadingRow = within(table).getByText('1').closest('tr') as HTMLElement;
    const processingRow = within(table).getByText('3').closest('tr') as HTMLElement;
    const failedRow = within(table).getByText('4').closest('tr') as HTMLElement;

    expect((within(reviewRow).getByRole('checkbox', { name: /批量导出.*2/ }) as HTMLInputElement).disabled).toBe(false);
    expect((within(doneRow).getByRole('checkbox', { name: /批量导出.*5/ }) as HTMLInputElement).disabled).toBe(false);
    expect((within(uploadingRow).getByRole('checkbox', { name: /批量导出.*1/ }) as HTMLInputElement).disabled).toBe(true);
    expect((within(processingRow).getByRole('checkbox', { name: /批量导出.*3/ }) as HTMLInputElement).disabled).toBe(true);
    expect((within(failedRow).getByRole('checkbox', { name: /批量导出.*4/ }) as HTMLInputElement).disabled).toBe(true);
  });

  it('disables batch export button when 0 selected; updates label with count when 1+ selected', async () => {
    const user = userEvent.setup();
    renderTaskList();

    const table = await screen.findByRole('table', { name: '任务列表' });
    const reviewRow = within(table).getByText('2').closest('tr') as HTMLElement;
    const doneRow = within(table).getByText('5').closest('tr') as HTMLElement;

    const button = screen.getByRole('button', { name: /批量导出/ }) as HTMLButtonElement;
    expect(button.disabled).toBe(true);
    expect(button.textContent).toContain('批量导出');
    expect(button.textContent).toContain('0');

    await user.click(within(reviewRow).getByRole('checkbox', { name: /批量导出.*2/ }));
    expect(button.disabled).toBe(false);
    expect(button.textContent).toContain('1');

    await user.click(within(doneRow).getByRole('checkbox', { name: /批量导出.*5/ }));
    expect(button.textContent).toContain('2');
  });

  it('calls exportTasksBatchZip with selected ids and triggers zip download on success', async () => {
    const user = userEvent.setup();
    const batchSpy = vi.fn();
    const fakeBlob = new Blob(['PK fake zip'], { type: 'application/zip' });
    const urlSpy = vi.spyOn(URL, 'createObjectURL').mockReturnValue('blob:fake-url');
    const clickSpy = vi.spyOn(HTMLAnchorElement.prototype, 'click').mockImplementation(() => {});

    server.use(
      mockTasks(),
      http.post('*/api/tasks/export/batch-zip', async ({ request }) => {
        const body = (await request.json()) as { task_ids: string[] };
        batchSpy(body.task_ids);
        return new HttpResponse(fakeBlob, {
          status: 200,
          headers: { 'Content-Type': 'application/zip' }
        });
      })
    );
    render(<TasksPage />);

    const table = await screen.findByRole('table', { name: '任务列表' });
    const reviewRow = within(table).getByText('2').closest('tr') as HTMLElement;
    const doneRow = within(table).getByText('5').closest('tr') as HTMLElement;
    await user.click(within(reviewRow).getByRole('checkbox', { name: /批量导出.*2/ }));
    await user.click(within(doneRow).getByRole('checkbox', { name: /批量导出.*5/ }));
    await user.click(screen.getByRole('button', { name: /批量导出.*2/ }));

    await waitFor(() => expect(batchSpy).toHaveBeenCalledWith(['2', '5']));
    await waitFor(() => expect(urlSpy).toHaveBeenCalledWith(fakeBlob));
    expect(clickSpy).toHaveBeenCalled();
    // 摘要条出现
    expect(screen.getByText(/已导出 2 个任务/)).toBeTruthy();

    urlSpy.mockRestore();
    clickSpy.mockRestore();
  });

  it('shows error message on batch export failure without changing the task list', async () => {
    const user = userEvent.setup();
    server.use(
      mockTasks(),
      http.post('*/api/tasks/export/batch-zip', () =>
        HttpResponse.json(
          { error: { code: 'EXPORT_VALIDATION_FAILED', message: '批量导出存在不可导出任务', details: {} } },
          { status: 400 }
        )
      )
    );
    render(<TasksPage />);

    const table = await screen.findByRole('table', { name: '任务列表' });
    const reviewRow = within(table).getByText('2').closest('tr') as HTMLElement;
    await user.click(within(reviewRow).getByRole('checkbox', { name: /批量导出.*2/ }));
    await user.click(screen.getByRole('button', { name: /批量导出/ }));

    expect(await screen.findByText('批量导出存在不可导出任务')).toBeTruthy();
    // 任务列表还在
    expect(screen.getByText('2')).toBeTruthy();
  });

  it('clears the summary banner when the close button is clicked', async () => {
    const user = userEvent.setup();
    const fakeBlob = new Blob(['PK fake zip'], { type: 'application/zip' });
    const urlSpy = vi.spyOn(URL, 'createObjectURL').mockReturnValue('blob:fake-url');
    const clickSpy = vi.spyOn(HTMLAnchorElement.prototype, 'click').mockImplementation(() => {});

    server.use(
      mockTasks(),
      http.post('*/api/tasks/export/batch-zip', () =>
        new HttpResponse(fakeBlob, {
          status: 200,
          headers: { 'Content-Type': 'application/zip' }
        })
      )
    );
    render(<TasksPage />);

    const table = await screen.findByRole('table', { name: '任务列表' });
    const reviewRow = within(table).getByText('2').closest('tr') as HTMLElement;
    await user.click(within(reviewRow).getByRole('checkbox', { name: /批量导出.*2/ }));
    await user.click(screen.getByRole('button', { name: /批量导出/ }));

    expect(await screen.findByText(/已导出 1 个任务/)).toBeTruthy();
    const closeButton = screen.getByRole('button', { name: '关闭批量导出摘要' });
    await user.click(closeButton);
    await waitFor(() => expect(screen.queryByText(/已导出 1 个任务/)).toBeNull());

    urlSpy.mockRestore();
    clickSpy.mockRestore();
  });

  it('keeps selected task ids after silent polling refresh', async () => {
    const user = userEvent.setup();
    let requestCount = 0;
    server.use(
      http.get('*/api/tasks', () => {
        requestCount += 1;
        return HttpResponse.json({ success: true, data: { tasks: taskFixtures } });
      })
    );
    render(<TasksPage />);

    const table = await screen.findByRole('table', { name: '任务列表' });
    const reviewRow = within(table).getByText('2').closest('tr') as HTMLElement;
    const reviewCheckbox = within(reviewRow).getByRole('checkbox', { name: /批量导出.*2/ });
    await user.click(reviewCheckbox);
    expect((reviewCheckbox as HTMLInputElement).checked).toBe(true);
    expect(requestCount).toBeGreaterThanOrEqual(1);

    // 等一次轮询再触发(useSilentPolling 5s 间隔)
    vi.useFakeTimers({ shouldAdvanceTime: true });
    Object.defineProperty(document, 'visibilityState', { configurable: true, value: 'visible' });
    await act(async () => {
      vi.advanceTimersByTime(5500);
    });
    await act(async () => {
      vi.advanceTimersByTime(5500);
    });
    vi.useRealTimers();

    // 重新查询,验证选择状态保持(只要 TasksPage 状态未重置即可)
    const tableAfter = await screen.findByRole('table', { name: '任务列表' });
    const reviewRowAfter = within(tableAfter).getByText('2').closest('tr') as HTMLElement;
    const checkboxAfter = within(reviewRowAfter).getByRole('checkbox', { name: /批量导出.*2/ });
    expect((checkboxAfter as HTMLInputElement).checked).toBe(true);
  });
});
