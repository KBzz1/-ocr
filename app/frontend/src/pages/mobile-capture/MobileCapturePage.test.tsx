import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { cleanup, render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { http, HttpResponse } from 'msw';

import { server } from '../../../tests/setupTests';
import type { UploadedImage } from '../../api/mobileUpload';
import { MobileCapturePage } from './MobileCapturePage';

const originalCreateObjectURL = URL.createObjectURL;

afterEach(() => {
  cleanup();
  if (originalCreateObjectURL) {
    Object.defineProperty(URL, 'createObjectURL', {
      configurable: true,
      value: originalCreateObjectURL
    });
  } else {
    Reflect.deleteProperty(URL, 'createObjectURL');
  }
});

beforeEach(() => {
  mockUploadStatus();
});

function stubBlobUrls() {
  let counter = 0;
  Object.defineProperty(URL, 'createObjectURL', {
    configurable: true,
    value: vi.fn(() => {
      counter += 1;
      return `blob:preview-${counter}`;
    })
  });
}

function mockUploadRoutes(onUpload?: () => void) {
  let pageNo = 0;
  server.use(
    http.post('*/api/mobile-upload/task_001/images', () => {
      onUpload?.();
      pageNo += 1;
      return HttpResponse.json({
        success: true,
        data: {
          page_id: `page_${String(pageNo).padStart(3, '0')}`,
          task_id: 'task_001',
          page_no: pageNo,
          uploaded_at: '2026-05-19T10:00:00+08:00'
        }
      });
    }),
    http.post('*/api/mobile-upload/task_001/finish', () =>
      HttpResponse.json({
        success: true,
        data: {
          task_id: 'task_001',
          status: 'processing',
          created_at: '2026-05-19T10:00:00+08:00',
          page_count: pageNo
        }
      })
    )
  );
}

function mockUploadStatus(images: UploadedImage[] = []) {
  server.use(
    http.get('*/api/mobile-upload/task_001', () =>
      HttpResponse.json({
        success: true,
        data: {
          task_id: 'task_001',
          status: 'uploading',
          page_count: images.length,
          images
        }
      })
    )
  );
}

describe('MobileCapturePage', () => {
  it('queues selected images and uploads them only when finishing', async () => {
    stubBlobUrls();
    let uploadCount = 0;
    mockUploadRoutes(() => {
      uploadCount += 1;
    });
    render(<MobileCapturePage taskId="task_001" token="token_001" />);
    const file = new File(['png'], 'page-1.png', { type: 'image/png' });

    await userEvent.upload(screen.getByLabelText('拍照/选择图片'), file);

    expect(await screen.findByText('第 1 页')).toBeTruthy();
    expect(screen.getByText('待上传')).toBeTruthy();
    expect(screen.getByText('page-1.png')).toBeTruthy();
    expect(uploadCount).toBe(0);

    await userEvent.click(screen.getByRole('button', { name: '完成上传' }));

    await waitFor(() => {
      expect(uploadCount).toBe(1);
    });
    expect(await screen.findByText('上传已完成，请回到电脑端查看处理结果')).toBeTruthy();
    expect(screen.queryByText('四边形框选')).toBeNull();
    expect(screen.queryByText('重新框选')).toBeNull();
    expect(screen.queryByText('拖拽')).toBeNull();
  });

  it('disables finish until at least one image uploaded', () => {
    render(<MobileCapturePage taskId="task_001" token="token_001" />);

    expect((screen.getByRole('button', { name: '完成上传' }) as HTMLButtonElement).disabled).toBe(true);
  });

  it('loads existing uploaded task images when opened from QR code', async () => {
    mockUploadStatus([
      {
        page_id: 'page_001',
        task_id: 'task_001',
        page_no: 1,
        preview_url: '/api/tasks/task_001/images/page_001',
        uploaded_at: '2026-05-20T20:55:00+08:00'
      }
    ]);

    render(<MobileCapturePage taskId="task_001" token="token_001" />);

    expect(await screen.findByText('第 1 页')).toBeTruthy();
    expect(screen.getAllByText('已选择 1 张图片').length).toBeGreaterThan(0);
  });

  it('deletes queued images before upload', async () => {
    stubBlobUrls();
    render(<MobileCapturePage taskId="task_001" token="token_001" />);
    const file = new File(['png'], 'page-1.png', { type: 'image/png' });

    await userEvent.upload(screen.getByLabelText('拍照/选择图片'), file);
    expect(await screen.findByText('第 1 页')).toBeTruthy();

    await userEvent.click(screen.getByRole('button', { name: '删除第 1 页' }));

    expect(screen.queryByText('第 1 页')).toBeNull();
    expect(screen.getByText('暂未上传图片')).toBeTruthy();
  });

  it('finish upload tells user to return to desktop', async () => {
    mockUploadRoutes();
    render(
      <MobileCapturePage
        taskId="task_001"
        token="token_001"
        initialImages={[{
          page_id: 'page_001',
          task_id: 'task_001',
          page_no: 1,
          uploaded_at: '2026-05-19T10:00:00+08:00'
        }]}
      />
    );

    await userEvent.click(screen.getByRole('button', { name: '完成上传' }));

    expect(await screen.findByText('上传已完成，请回到电脑端查看处理结果')).toBeTruthy();
  });

  it('asks for confirmation before clearing all images', async () => {
    let deleteCount = 0;
    server.use(
      http.delete('*/api/mobile-upload/task_001/images/page_001', () => {
        deleteCount += 1;
        return HttpResponse.json({
          success: true,
          data: {
            task_id: 'task_001',
            status: 'uploading',
            page_count: 0,
            images: []
          }
        });
      })
    );

    render(
      <MobileCapturePage
        taskId="task_001"
        token="token_001"
        initialImages={[{
          page_id: 'page_001',
          task_id: 'task_001',
          page_no: 1,
          uploaded_at: '2026-05-19T10:00:00+08:00'
        }]}
      />
    );

    expect(screen.getByText('第 1 页')).toBeTruthy();

    await userEvent.click(screen.getByRole('button', { name: '清除所有图片' }));
    expect(screen.getByRole('alertdialog', { name: '清除所有图片？' })).toBeTruthy();

    await userEvent.click(screen.getByRole('button', { name: '取消' }));
    expect(screen.getByText('第 1 页')).toBeTruthy();
    expect(deleteCount).toBe(0);

    await userEvent.click(screen.getByRole('button', { name: '清除所有图片' }));
    await userEvent.click(screen.getByRole('button', { name: '确认清除' }));

    await waitFor(() => expect(deleteCount).toBe(1));
    expect(screen.queryByText('第 1 页')).toBeNull();
    expect(screen.getByText('暂未上传图片')).toBeTruthy();
  });

  it('handles partial deletion failure by syncing server state', async () => {
    let deleteCalls = 0;
    server.use(
      http.delete('*/api/mobile-upload/task_001/images/:pageId', () => {
        deleteCalls += 1;
        if (deleteCalls === 2) {
          // second delete fails with a JSON error body
          return HttpResponse.json(
            { error: { code: 'INTERNAL_SERVER_ERROR', message: '服务器内部错误', details: {} } },
            { status: 500 }
          );
        }
        return HttpResponse.json({
          success: true,
          data: {
            task_id: 'task_001',
            status: 'uploading',
            page_count: 2 - deleteCalls,
            images: deleteCalls === 1
              ? [{ page_id: 'page_002', task_id: 'task_001', page_no: 1, uploaded_at: '2026-05-19T10:00:00+08:00' }]
              : []
          }
        });
      }),
      // 失败后重新同步服务端状态的 GET handler
      http.get('*/api/mobile-upload/task_001', () =>
        HttpResponse.json({
          success: true,
          data: {
            task_id: 'task_001',
            status: 'uploading',
            page_count: 1,
            images: [{ page_id: 'page_002', task_id: 'task_001', page_no: 1, uploaded_at: '2026-05-19T10:00:00+08:00' }]
          }
        })
      )
    );

    render(
      <MobileCapturePage
        taskId="task_001"
        token="token_001"
        initialImages={[
          { page_id: 'page_001', task_id: 'task_001', page_no: 1, uploaded_at: '2026-05-19T10:00:00+08:00' },
          { page_id: 'page_002', task_id: 'task_001', page_no: 2, uploaded_at: '2026-05-19T10:00:00+08:00' }
        ]}
      />
    );

    expect(screen.getByText('第 1 页')).toBeTruthy();
    expect(screen.getByText('第 2 页')).toBeTruthy();

    await userEvent.click(screen.getByRole('button', { name: '清除所有图片' }));
    await userEvent.click(screen.getByRole('button', { name: '确认清除' }));

    // 第二个删除失败 → 应显示错误(error message from ApiError body)
    await waitFor(() => {
      expect(screen.getByText(/服务器内部错误/i)).toBeTruthy();
    });
    // 重新同步后,服务端返回了 page_002(未删掉的那张,重新编号为第1页)
    expect(await screen.findByText('第 1 页')).toBeTruthy();
    // page_001 已被删除,不应出现 "第 2 页"
    expect(screen.queryByText('第 2 页')).toBeNull();
  });

  it('shows document type label read-only and does not render template selector', async () => {
    server.use(
      http.get('*/api/mobile-upload/task_001', () => HttpResponse.json({
        success: true,
        data: {
          task_id: 'task_001',
          status: 'uploading',
          page_count: 0,
          images: [],
          document_type: 'copd_admission_record',
          document_type_label: '入院记录',
          schema_version: 'copd.v1'
        }
      }))
    );

    render(<MobileCapturePage taskId="task_001" token="token_001" />);

    expect(await screen.findByText('记录类型')).toBeTruthy();
    expect(screen.getByText('入院记录')).toBeTruthy();
    expect(screen.queryByLabelText('文书模板')).toBeNull();
    expect(screen.queryByRole('combobox')).toBeNull();
  });
});
