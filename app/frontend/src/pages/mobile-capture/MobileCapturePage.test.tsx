import { afterEach } from 'vitest';
import { act, cleanup, render, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { http, HttpResponse } from 'msw';
import { describe, expect, it, vi } from 'vitest';

import {
  activeSession,
  mockGetCaptureSession
} from '../../../tests/fixtures/sessions';
import {
  makeImageFile,
  makeLargeImageFile,
  mockUploadCapturePageSuccess
} from '../../../tests/fixtures/uploads';
import { server } from '../../../tests/setupTests';
import { MobileCapturePlaceholder as MobileCapturePage } from './MobileCapturePlaceholder';

afterEach(() => {
  cleanup();
});

function jsonOk(data: unknown) {
  return HttpResponse.json({ success: true, data });
}

function renderMobileCapture(path = '/mobile/sessions/sess_001') {
  window.history.pushState({}, '', path);
  return render(<MobileCapturePage />);
}

function fileInput(label: string) {
  return screen.getByLabelText(label) as HTMLInputElement;
}

function expectButtonDisabled(name: string, disabled: boolean) {
  expect((screen.getByRole('button', { name }) as HTMLButtonElement).disabled).toBe(disabled);
}

async function selectImage(label = '选择已有图片', file = makeImageFile()) {
  const user = userEvent.setup();
  await user.upload(fileInput(label), file);
  return user;
}

/** Create a drag event compatible with jsdom (polyfills DragEvent if absent). */
function createDragEvent(type: string) {
  if (typeof DragEvent === 'function') {
    return new DragEvent(type, { bubbles: true });
  }
  // Fallback for jsdom without DragEvent
  const event = new Event(type, { bubbles: true }) as DragEvent;
  Object.defineProperty(event, 'dataTransfer', {
    value: {
      setData: () => {},
      getData: () => '',
      clearData: () => {},
      effectAllowed: 'move',
      dropEffect: 'move',
      items: [],
      types: [],
      files: [],
      setDragImage: () => {}
    },
    writable: false
  });
  return event;
}

describe('MobileCapturePage', () => {
  it('wires topbar back and help actions', async () => {
    const user = userEvent.setup();
    const backSpy = vi.spyOn(window.history, 'back').mockImplementation(() => undefined);
    server.use(mockGetCaptureSession({ ...activeSession, page_count: 0 }));
    renderMobileCapture();

    await screen.findByText('采集会话进行中');
    await user.click(screen.getByRole('button', { name: '帮助' }));
    expect(screen.getByText('拍照或选择图片后，请确认四个角点覆盖病历页面。')).toBeTruthy();

    await user.click(screen.getByRole('button', { name: '返回' }));
    expect(backSpy).toHaveBeenCalledTimes(1);
    backSpy.mockRestore();
  });

  it('loads active, expired, missing and locked session states', async () => {
    const expired = { ...activeSession, status: 'expired' as const, page_count: 0 };
    const locked = {
      ...activeSession,
      status: 'locked' as const,
      page_count: 1,
      pages: [{ page_id: 'page_001', page_no: 1 }]
    };

    server.use(mockGetCaptureSession({ ...activeSession, page_count: 0 }));
    const { unmount } = renderMobileCapture();
    expect(await screen.findByText('采集会话进行中')).toBeTruthy();
    expect(screen.getByText('已采集 0 页')).toBeTruthy();
    expectButtonDisabled('拍摄/选择图片', false);
    unmount();
    cleanup();

    server.use(mockGetCaptureSession(expired));
    const expiredRender = renderMobileCapture();
    expect(await screen.findByText('采集会话已过期')).toBeTruthy();
    expectButtonDisabled('拍摄/选择图片', true);
    expiredRender.unmount();
    cleanup();

    server.use(
      http.get('*/api/capture-sessions/sess_invalid', () =>
        HttpResponse.json(
          { error: { code: 'NOT_FOUND', message: '不存在', details: {} } },
          { status: 404 }
        )
      )
    );
    const invalidRender = renderMobileCapture('/mobile/sessions/sess_invalid');
    expect(await screen.findByText('无效的采集链接，请重新扫描二维码')).toBeTruthy();
    expectButtonDisabled('拍摄/选择图片', true);
    invalidRender.unmount();
    cleanup();

    server.use(mockGetCaptureSession(locked));
    renderMobileCapture();
    expect(await screen.findByText('采集已完成，请在电脑端查看')).toBeTruthy();
    expect(screen.queryByRole('button', { name: '删除第 1 页' })).toBeNull();
    expect(screen.queryByRole('button', { name: /上移/ })).toBeNull();
    expect(screen.queryByRole('button', { name: /下移/ })).toBeNull();
    expect(screen.queryByRole('button', { name: '补拍页面' })).toBeNull();
  });

  it('previews selected images, blocks invalid files and uploads quad metadata once', async () => {
    const formDataSet = vi.spyOn(FormData.prototype, 'set');
    let uploadCalls = 0;
    server.use(
      mockGetCaptureSession({ ...activeSession, page_count: 0, pages: [] }),
      mockUploadCapturePageSuccess(activeSession.session_id, () => {
        uploadCalls += 1;
      })
    );
    renderMobileCapture();

    await screen.findByText('采集会话进行中');
    await userEvent.setup({ applyAccept: false }).upload(
      fileInput('拍摄/选择图片'),
      new File(['pdf'], 'record.pdf', { type: 'application/pdf' })
    );
    expect(screen.getByText('不支持的文件类型')).toBeTruthy();

    await userEvent.setup().upload(fileInput('拍摄/选择图片'), makeLargeImageFile());
    expect(screen.getByText('图片过大（最大 20MB）')).toBeTruthy();

    await selectImage('拍摄/选择图片');
    expect(screen.getByAltText('待上传病历页面预览')).toBeTruthy();
    expect(screen.getByLabelText('四边形框选区域')).toBeTruthy();
    expect(screen.queryByRole('slider')).toBeNull();
    expect(screen.queryByLabelText(/坐标/)).toBeNull();

    const uploadButton = screen.getByRole('button', { name: '确认上传' });
    await userEvent.setup().dblClick(uploadButton);

    await waitFor(() => expect(uploadCalls).toBe(1));
    expect(formDataSet).toHaveBeenCalledWith('image', expect.any(File));
    expect(formDataSet).toHaveBeenCalledWith('image_width', '1000');
    expect(formDataSet).toHaveBeenCalledWith('image_height', '1400');
    const quadCall = formDataSet.mock.calls.find(([name]) => name === 'quad_points');
    expect(quadCall).toBeTruthy();
    expect(JSON.parse(String(quadCall?.[1]))).toEqual([
      { x: 100, y: 140 },
      { x: 900, y: 140 },
      { x: 900, y: 1260 },
      { x: 100, y: 1260 }
    ]);
    expect(await screen.findByText('第 1 页')).toBeTruthy();
    expect(screen.getByText('已上传')).toBeTruthy();
    formDataSet.mockRestore();
  });

  it('keeps a failed pending page and retries only that page', async () => {
    let uploadCalls = 0;
    server.use(
      mockGetCaptureSession({
        ...activeSession,
        page_count: 1,
        pages: [{ page_id: 'page_uploaded', page_no: 1 }]
      }),
      http.post('*/api/mobile/:sessionId/pages', ({ params }) => {
        if (params.sessionId !== 'sess_001') {
          return HttpResponse.json(
            { error: { code: 'NOT_FOUND', message: '会话不存在', details: {} } },
            { status: 404 }
          );
        }
        uploadCalls += 1;
        if (uploadCalls === 1) {
          return HttpResponse.json(
            {
              error: {
                code: 'UPLOAD_FAILED',
                message: '上传失败，请重试',
                details: {}
              }
            },
            { status: 500 }
          );
        }

        return HttpResponse.json({
          success: true,
          data: { page_id: 'page_retry', page_index: 2, status: 'uploaded' }
        });
      })
    );
    renderMobileCapture();

    await screen.findByText('第 1 页');
    await selectImage('拍摄/选择图片');
    await userEvent.setup().click(screen.getByRole('button', { name: '确认上传' }));

    expect((await screen.findAllByText('上传失败，请重试')).length).toBeGreaterThan(0);
    const failedItem = screen.getByLabelText('第 2 页 上传失败');
    expect(within(failedItem).getByRole('button', { name: '重试第 2 页' })).toBeTruthy();

    await userEvent.setup().click(within(failedItem).getByRole('button', { name: '重试第 2 页' }));

    await waitFor(() => expect(uploadCalls).toBe(2));
    expect(screen.getAllByText('已上传')).toHaveLength(2);
  });

  it('manages uploaded page order, deletion, supplement capture and locked finish state', async () => {
    const confirmSpy = vi.spyOn(window, 'confirm').mockReturnValue(true);
    let finishCalls = 0;
    server.use(
      mockGetCaptureSession({
        ...activeSession,
        page_count: 2,
        pages: [
          { page_id: 'page_a', page_no: 1 },
          { page_id: 'page_b', page_no: 2 }
        ]
      }),
      mockUploadCapturePageSuccess(),
      http.delete('*/api/capture-sessions/sess_001/pages/:pageId', () =>
        jsonOk({ ok: true })
      ),
      http.put('*/api/capture-sessions/sess_001/pages/order', () =>
        jsonOk({ ok: true })
      ),
      http.post('*/api/mobile/sess_001/finish', () => {
        finishCalls += 1;
        return HttpResponse.json({
          success: true,
          data: { session_id: 'sess_001', status: 'locked', task_id: 'task_001' }
        });
      })
    );
    renderMobileCapture();

    await screen.findByText('第 1 页');

    // Old move buttons should not exist
    expect(screen.queryByRole('button', { name: /上移/ })).toBeNull();
    expect(screen.queryByRole('button', { name: /下移/ })).toBeNull();
    expect(screen.queryByRole('button', { name: '补拍页面' })).toBeNull();

    // New inline buttons should exist
    expect(screen.getByRole('button', { name: /补拍第 1 页/ })).toBeTruthy();
    expect(screen.getByRole('button', { name: /重新框选第 1 页/ })).toBeTruthy();
    expect(screen.getByRole('button', { name: /删除第 1 页/ })).toBeTruthy();

    // Delete a page
    await userEvent.setup().click(screen.getByRole('button', { name: '删除第 1 页' }));
    expect(confirmSpy).toHaveBeenCalled();
    await waitFor(() => expect(screen.getAllByText('已上传')).toHaveLength(1));
    expect(screen.getByText('已采集 1 页')).toBeTruthy();

    // Supplement via inline button
    await userEvent.setup().click(screen.getByRole('button', { name: '补拍第 1 页' }));
    await selectImage('拍照', makeImageFile('supplement.jpg'));
    await userEvent.setup().click(screen.getByRole('button', { name: '确认上传' }));
    expect(await screen.findByText('第 2 页')).toBeTruthy();

    // Finish
    const finishButton = screen.getByRole('button', { name: '完成采集' });
    await userEvent.setup().dblClick(finishButton);
    await waitFor(() => expect(finishCalls).toBe(1));
    expect(screen.getByText('采集完成，请在电脑端继续审核')).toBeTruthy();
    expectButtonDisabled('拍摄/选择图片', true);
    expect(screen.queryByRole('button', { name: /删除第/ })).toBeNull();
    confirmSpy.mockRestore();
  });

  it('prevents finishing with zero uploaded pages', async () => {
    let finishCalls = 0;
    server.use(
      mockGetCaptureSession({ ...activeSession, page_count: 0, pages: [] }),
      http.post('*/api/mobile/sess_001/finish', () => {
        finishCalls += 1;
        return HttpResponse.json({
          success: true,
          data: { session_id: 'sess_001', status: 'locked', task_id: 'task_001' }
        });
      })
    );
    renderMobileCapture();

    await screen.findByText('已采集 0 页');
    await userEvent.setup().click(screen.getByRole('button', { name: '完成采集' }));
    expect(screen.getByText('请至少采集一页病历')).toBeTruthy();
    expect(finishCalls).toBe(0);
  });

  it('reorders uploaded pages with drag handle', async () => {
    const calls: string[][] = [];
    server.use(
      mockGetCaptureSession({
        ...activeSession,
        page_count: 2,
        pages: [
          { page_id: 'page_a', page_no: 1 },
          { page_id: 'page_b', page_no: 2 }
        ]
      }),
      http.put('*/api/capture-sessions/sess_001/pages/order', async ({ request }) => {
        const body = await request.json() as { page_ids: string[] };
        calls.push(body.page_ids);
        return HttpResponse.json({ success: true, data: { ok: true } });
      })
    );

    renderMobileCapture();
    await screen.findByText('第 1 页');
    const source = screen.getByLabelText('拖拽第 2 页');
    const target = screen.getByLabelText('第 1 页 已上传');

    // Dispatch drag events with act to flush React state between events
    await act(() => {
      source.dispatchEvent(createDragEvent('dragstart'));
    });
    await act(() => {
      target.dispatchEvent(createDragEvent('dragover'));
    });
    await act(() => {
      target.dispatchEvent(createDragEvent('drop'));
    });

    await waitFor(() => expect(calls).toEqual([['page_b', 'page_a']]));
  });

  it('uses capture-session routes for delete and reorder', async () => {
    const calls: string[] = [];
    const confirmSpy = vi.spyOn(window, 'confirm').mockReturnValue(true);
    server.use(
      mockGetCaptureSession({
        ...activeSession,
        page_count: 2,
        pages: [
          { page_id: 'page_a', page_no: 1 },
          { page_id: 'page_b', page_no: 2 }
        ]
      }),
      http.delete('*/api/capture-sessions/sess_001/pages/:pageId', ({ request }) => {
        calls.push(new URL(request.url).pathname);
        return jsonOk({ ok: true });
      }),
      http.put('*/api/capture-sessions/sess_001/pages/order', async ({ request }) => {
        calls.push(new URL(request.url).pathname);
        expect(await request.json()).toEqual({ page_ids: ['page_b', 'page_a'] });
        return jsonOk({ ok: true });
      })
    );

    renderMobileCapture();
    await screen.findByText('第 1 页');

    // Drag page 2 to page 1 position
    const source = screen.getByLabelText('拖拽第 2 页');
    const target = screen.getByLabelText('第 1 页 已上传');

    await act(() => {
      source.dispatchEvent(createDragEvent('dragstart'));
    });
    await act(() => {
      target.dispatchEvent(createDragEvent('dragover'));
    });
    await act(() => {
      target.dispatchEvent(createDragEvent('drop'));
    });

    // Click delete on the now-first page (was page_b after reorder)
    await userEvent.setup().click(screen.getByRole('button', { name: '删除第 1 页' }));

    await waitFor(() => expect(calls).toEqual([
      '/api/capture-sessions/sess_001/pages/order',
      '/api/capture-sessions/sess_001/pages/page_b',
    ]));
    confirmSpy.mockRestore();
  });
});
