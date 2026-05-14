import { render, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import {
  confirmedExportTask,
  exportedJsonTask,
  mockExcelExport,
  mockExportIntegrityError,
  mockJsonExport,
  unconfirmedExportTask
} from '../../../tests/fixtures/export';
import { server } from '../../../tests/setupTests';
import { ExportPanel, type ExportTaskView } from './ExportPanel';

function renderPanel(task: ExportTaskView = confirmedExportTask) {
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

  it('shows JSON and Excel export actions for confirmed tasks', () => {
    renderPanel();

    expect((screen.getByRole('button', { name: '导出 JSON' }) as HTMLButtonElement).disabled).toBe(
      false
    );
    expect((screen.getByRole('button', { name: '导出 Excel' }) as HTMLButtonElement).disabled).toBe(
      false
    );
  });

  it('blocks unconfirmed exports and explains that review must be confirmed first', async () => {
    const user = userEvent.setup();
    renderPanel(unconfirmedExportTask);

    expect((screen.getByRole('button', { name: '导出 JSON' }) as HTMLButtonElement).disabled).toBe(
      true
    );
    expect((screen.getByRole('button', { name: '导出 Excel' }) as HTMLButtonElement).disabled).toBe(
      true
    );
    expect(screen.getByText('请先确认审核')).not.toBeNull();

    await user.click(screen.getByRole('button', { name: '导出 JSON' }));
    expect(createObjectUrl).not.toHaveBeenCalled();
  });

  it('shows review completeness counts before export', () => {
    renderPanel(unconfirmedExportTask);

    const summary = screen.getByLabelText('导出前完整性提示');
    expect(within(summary).getByText('未审核 2')).not.toBeNull();
    expect(within(summary).getByText('存疑 1')).not.toBeNull();
    expect(within(summary).getByText('为空 1')).not.toBeNull();
    expect(within(summary).getByText('未定位来源 3')).not.toBeNull();
  });

  it('downloads JSON through the backend export endpoint and shows the latest export record', async () => {
    const user = userEvent.setup();
    server.use(mockJsonExport('task-confirmed'));
    renderPanel();

    await user.click(screen.getByRole('button', { name: '导出 JSON' }));

    await waitFor(() => expect(clickSpy).toHaveBeenCalledTimes(1));
    expect(createObjectUrl).toHaveBeenCalledWith(expect.any(Blob));
    expect(screen.getByText(/最近导出/).textContent).toContain('JSON');
  });

  it('downloads Excel through the backend export endpoint without creating spreadsheets in the browser', async () => {
    const user = userEvent.setup();
    server.use(mockExcelExport('task-confirmed'));
    renderPanel();

    await user.click(screen.getByRole('button', { name: '导出 Excel' }));

    await waitFor(() => expect(clickSpy).toHaveBeenCalledTimes(1));
    expect(createObjectUrl).toHaveBeenCalledWith(expect.any(Blob));
    expect(screen.getByText(/最近导出/).textContent).toContain('Excel');
  });

  it('shows backend integrity errors and does not trigger a download', async () => {
    const user = userEvent.setup();
    server.use(mockExportIntegrityError('task-confirmed', 'json'));
    renderPanel();

    await user.click(screen.getByRole('button', { name: '导出 JSON' }));

    expect((await screen.findByRole('alert')).textContent).toContain('导出失败');
    expect(screen.getByRole('alert').textContent).toContain('请先确认审核');
    expect(createObjectUrl).not.toHaveBeenCalled();
    expect(clickSpy).not.toHaveBeenCalled();
  });

  it('keeps reviewed data visible when export fails', async () => {
    const user = userEvent.setup();
    server.use(mockExportIntegrityError('task-confirmed', 'excel'));
    renderPanel();

    expect(screen.getByText('已审核数据保留在本地任务中')).not.toBeNull();
    await user.click(screen.getByRole('button', { name: '导出 Excel' }));

    expect((await screen.findByRole('alert')).textContent).toContain('导出失败');
    expect(screen.getByText('已审核数据保留在本地任务中')).not.toBeNull();
  });

  it('renders an existing latest export time and format', () => {
    renderPanel(exportedJsonTask);

    expect(screen.getByText(/最近导出/).textContent).toContain('JSON');
    expect(screen.getByText(/最近导出/).textContent).toContain('2026/05/14 10:30');
  });
});
