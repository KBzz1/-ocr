import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import {
  doneExportTask,
  mockExcelExport,
  mockExportIntegrityError,
  mockJsonExport,
  processingExportTask,
  reviewExportTask
} from '../../../tests/fixtures/export';
import { server } from '../../../tests/setupTests';
import { ExportPanel, type ExportTaskView } from './ExportPanel';

function renderPanel(task: ExportTaskView = reviewExportTask) {
  return render(<ExportPanel task={task} />);
}

describe('ExportPanel', () => {
  const createObjectUrl = vi.fn(() => 'blob:export-file');
  const revokeObjectUrl = vi.fn();
  let clickSpy: ReturnType<typeof vi.spyOn>;

  beforeEach(() => {
    Object.defineProperty(URL, 'createObjectURL', {
      configurable: true,
      value: createObjectUrl
    });
    Object.defineProperty(URL, 'revokeObjectURL', {
      configurable: true,
      value: revokeObjectUrl
    });
    clickSpy = vi.spyOn(HTMLAnchorElement.prototype, 'click').mockImplementation(() => {});
    createObjectUrl.mockClear();
    revokeObjectUrl.mockClear();
  });

  afterEach(() => {
    vi.restoreAllMocks();
  });

  it('shows JSON and Excel export actions for review and done tasks', () => {
    renderPanel(reviewExportTask);
    expect((screen.getByRole('button', { name: '导出 JSON' }) as HTMLButtonElement).disabled).toBe(false);
    expect((screen.getByRole('button', { name: '导出 Excel' }) as HTMLButtonElement).disabled).toBe(false);

    renderPanel(doneExportTask);
    expect(screen.getAllByRole('button', { name: '导出 JSON' }).at(-1)).toBeTruthy();
  });

  it('blocks processing exports', async () => {
    const user = userEvent.setup();
    renderPanel(processingExportTask);

    expect((screen.getByRole('button', { name: '导出 JSON' }) as HTMLButtonElement).disabled).toBe(true);
    expect(screen.getByText('待审核或已完成任务才可导出')).not.toBeNull();

    await user.click(screen.getByRole('button', { name: '导出 JSON' }));
    expect(createObjectUrl).not.toHaveBeenCalled();
  });

  it('downloads JSON and Excel through backend export endpoints', async () => {
    const user = userEvent.setup();
    server.use(mockJsonExport('task-review'), mockExcelExport('task-review'));
    renderPanel();

    await user.click(screen.getByRole('button', { name: '导出 JSON' }));
    await waitFor(() => expect(clickSpy).toHaveBeenCalledTimes(1));
    expect(screen.getByText(/最近导出/).textContent).toContain('JSON');

    await user.click(screen.getByRole('button', { name: '导出 Excel' }));
    await waitFor(() => expect(clickSpy).toHaveBeenCalledTimes(2));
    expect(screen.getByText(/最近导出/).textContent).toContain('Excel');
  });

  it('shows backend export errors and does not trigger a download', async () => {
    const user = userEvent.setup();
    server.use(mockExportIntegrityError('task-review', 'json'));
    renderPanel();

    await user.click(screen.getByRole('button', { name: '导出 JSON' }));

    expect((await screen.findByRole('alert')).textContent).toContain('导出失败');
    expect(createObjectUrl).not.toHaveBeenCalled();
    expect(clickSpy).not.toHaveBeenCalled();
  });
});
