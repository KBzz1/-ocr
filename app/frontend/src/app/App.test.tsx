import { render, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { http, HttpResponse } from 'msw';
import { describe, expect, it } from 'vitest';

import {
  activeSession,
  mockCreateCaptureSession,
  mockCreateCaptureSessionError,
  mockGetCaptureSession
} from '../../tests/fixtures/sessions';
import { mockSystemStatus, mockSystemStatusError } from '../../tests/fixtures/system';
import { mockTasks, taskFixtures } from '../../tests/fixtures/tasks';
import { server } from '../../tests/setupTests';
import { buildMobileSessionPath } from './routes';
import { App } from './App';

function renderWorkstation() {
  window.history.pushState({}, '', '/');
  server.use(mockSystemStatus(), mockTasks());
  return render(<App />);
}

async function expectTextPresent(text: string) {
  const matches = await screen.findAllByText(text);
  expect(matches.length).toBeGreaterThan(0);
}

function expectOverviewCount(label: string, count: string) {
  const overview = screen.getByLabelText('任务概览');
  const card = within(overview).getByText(label).closest('a');
  expect(card).not.toBeNull();
  expect((card as HTMLElement).textContent).toContain(count);
}

function expectPresent(element: HTMLElement | null) {
  expect(element).not.toBeNull();
}

function expectBodyNotToContain(pattern: RegExp | string) {
  if (typeof pattern === 'string') {
    expect(document.body.textContent ?? '').not.toContain(pattern);
    return;
  }
  expect(document.body.textContent ?? '').not.toMatch(pattern);
}

describe('Workstation data integration', () => {
  beforeEach(() => {
    window.history.pushState({}, '', '/');
  });

  it('renders mobile capture page for scanned QR mobile paths', async () => {
    server.use(mockGetCaptureSession({ ...activeSession, page_count: 0, pages: [] }));
    window.history.pushState({}, '', buildMobileSessionPath('sess_001'));
    render(<App />);

    expect(await screen.findByText('采集会话进行中')).toBeTruthy();
    expect(screen.queryByRole('button', { name: /新建采集/ })).toBeNull();
  });

  it('renders business system status without exposing addresses on the homepage', async () => {
    renderWorkstation();

    await expectTextPresent('系统已启动');
    await expectTextPresent('离线运行');
    await expectTextPresent('手机采集可用');
    expectBodyNotToContain(/https?:\/\/|localhost|127\.0\.0\.1|192\.168\./);
    expectBodyNotToContain(/mobile\/|capture\?session=/);
  });

  it('renders backend status errors without a misleading running state', async () => {
    server.use(mockSystemStatusError(), mockTasks([]));
    render(<App />);

    await expectTextPresent('系统状态异常');
    expect(screen.queryByText('手机采集可用')).toBeNull();
    expect((screen.getByRole('button', { name: /新建采集/ }) as HTMLButtonElement).disabled).toBe(true);
  });

  it('aggregates task overview and renders state actions from shared enums', async () => {
    renderWorkstation();

    await expectTextPresent('系统已启动');
    expectOverviewCount('待审核', '1');
    expectOverviewCount('处理中', '1');
    expectOverviewCount('处理失败', '1');
    expectOverviewCount('已导出', '1');

    const table = screen.getByRole('table');
    expectPresent(within(table).getByText('task-ready'));
    expectPresent(within(table).getByText('开始审核'));
    expectPresent(within(table).getByText('查看原因'));
    expectPresent(within(table).getByText('重新处理'));
    expectBodyNotToContain('查看日志');
  });

  it('renders workstation navigation and task actions as connected links', async () => {
    renderWorkstation();

    await expectTextPresent('系统已启动');
    expect(screen.getByRole('link', { name: /任务管理/ }).getAttribute('href')).toBe('/tasks');
    expect(screen.getByRole('link', { name: /待审核/ }).getAttribute('href')).toBe('/tasks?status=ready_for_review');
    expect(screen.getByRole('link', { name: '全部任务' }).getAttribute('href')).toBe('/tasks');
    expect(screen.getByRole('link', { name: '开始审核' }).getAttribute('href')).toBe('/tasks/task-ready/review');
    expect(screen.getByRole('link', { name: '导出结果' }).getAttribute('href')).toBe('/tasks/task-exported/export');
  });

  it('shows empty task copy when the task API returns no records', async () => {
    server.use(mockSystemStatus(), mockTasks([]));
    render(<App />);

    expectPresent(await screen.findByText('暂无任务'));
    expectPresent(screen.getByText('新建采集后，任务会显示在这里。'));
  });

  it('creates a capture session and opens the QR modal on demand', async () => {
    const user = userEvent.setup();
    server.use(mockSystemStatus(), mockTasks(taskFixtures), mockCreateCaptureSession());
    render(<App />);

    await expectTextPresent('系统已启动');
    await user.click(screen.getByRole('button', { name: /新建采集/ }));

    const dialog = await screen.findByRole('dialog', { name: '采集二维码' });
    const qrImage = (await within(dialog).findByRole('img', { name: '采集二维码' })) as HTMLImageElement;
    expect(qrImage.tagName).toBe('IMG');
    expect(qrImage.src).toMatch(/^data:image\/svg\+xml/);
    expectPresent(within(dialog).getByText('等待设备扫码'));
    expectPresent(within(dialog).getByText(/已上传页数 2 页/));
    expect(screen.queryByRole('button', { name: '结束会话' })).toBeNull();
    expectBodyNotToContain(/192\.168\.1\.5:8081\/mobile\/sess_001/);
    expect(qrImage.dataset.qrValue).toBe('http://127.0.0.1:5173/mobile/sessions/sess_001');
  });

  it('shows connection help and copyable mobile link only after request', async () => {
    const user = userEvent.setup();
    server.use(mockSystemStatus(), mockTasks([]), mockCreateCaptureSession());
    render(<App />);

    await user.click(await screen.findByRole('button', { name: /新建采集/ }));
    const dialog = await screen.findByRole('dialog', { name: '采集二维码' });

    expect(within(dialog).queryByText('手机访问链接')).toBeNull();
    await user.click(within(dialog).getByRole('button', { name: '手机无法连接？' }));

    expectPresent(within(dialog).getByText('手机访问链接'));
    expect((within(dialog).getByLabelText('手机访问链接') as HTMLInputElement).value).toBe(
      'http://127.0.0.1:5173/mobile/sessions/sess_001'
    );
  });

  it('rejects loopback QR URLs for mobile capture', async () => {
    const user = userEvent.setup();
    server.use(
      mockSystemStatus(),
      mockTasks([]),
      mockCreateCaptureSession({
        success: true,
        data: {
          session_id: 'sess_loopback',
          status: 'active',
          created_at: '2026-05-13T10:00:00+08:00',
          expires_at: '2026-05-13T10:30:00+08:00',
          qr_code_url: 'http://127.0.0.1:8081/mobile/sess_loopback',
          page_count: 0
        }
      })
    );
    render(<App />);

    await user.click(await screen.findByRole('button', { name: /新建采集/ }));

    expectPresent(await screen.findByText('创建采集会话失败，请重试'));
    expect(screen.queryByRole('dialog', { name: '采集二维码' })).toBeNull();
  });

  it('removes the QR modal from the homepage after closing and can reopen it from the current session card', async () => {
    const user = userEvent.setup();
    server.use(mockSystemStatus(), mockTasks([]), mockCreateCaptureSession());
    render(<App />);

    await user.click(await screen.findByRole('button', { name: /新建采集/ }));
    expectPresent(await screen.findByRole('dialog', { name: '采集二维码' }));

    await user.click(screen.getByRole('button', { name: '关闭' }));
    await waitFor(() =>
      expect(screen.queryByRole('dialog', { name: '采集二维码' })).toBeNull()
    );
    expect(screen.queryByRole('img', { name: '采集二维码' })).toBeNull();

    await user.click(screen.getByRole('button', { name: '查看二维码' }));
    expectPresent(await screen.findByRole('dialog', { name: '采集二维码' }));
  });

  it('clears the old QR when creating a new capture session fails', async () => {
    const user = userEvent.setup();
    server.use(mockSystemStatus(), mockTasks([]), mockCreateCaptureSession());
    render(<App />);

    await user.click(await screen.findByRole('button', { name: /新建采集/ }));
    expectPresent(await screen.findByRole('dialog', { name: '采集二维码' }));

    server.use(mockCreateCaptureSessionError());
    await user.click(screen.getByRole('button', { name: '重新生成二维码' }));

    expectPresent(await screen.findByText('创建采集会话失败，请重试'));
    expect(screen.queryByRole('dialog', { name: '采集二维码' })).toBeNull();
    expect(screen.queryByRole('img', { name: '采集二维码' })).toBeNull();
  });

  it('retries system status loading after service no response', async () => {
    const user = userEvent.setup();
    let statusCalls = 0;
    server.use(
      http.get('*/api/system/status', () => {
        statusCalls += 1;
        if (statusCalls === 1) {
          return HttpResponse.error();
        }
        return HttpResponse.json({
          success: true,
          data: {
            status: 'running',
            version: 'test',
            started_at: '2026-05-14T10:00:00+08:00',
            lan_addresses: ['192.168.1.5:8081']
          }
        });
      }),
      mockTasks([])
    );

    render(<App />);
    expect(await screen.findByText('服务无响应', { selector: 'h2' })).toBeTruthy();
    await user.click(screen.getByRole('button', { name: '重试' }));
    expect(await screen.findByText('系统已启动', { selector: 'h2' })).toBeTruthy();
    expect(statusCalls).toBeGreaterThanOrEqual(2);
  });
});
