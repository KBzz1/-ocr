import { afterEach, describe, expect, it, vi } from 'vitest';
import { cleanup, render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { http, HttpResponse } from 'msw';

import { server } from '../../../tests/setupTests';
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

function mockUploadRoutes() {
  let pageNo = 0;
  server.use(
    http.post('*/api/mobile-upload/task_001/images', () => {
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

describe('MobileCapturePage', () => {
  it('uploads selected images directly to task and shows upload order', async () => {
    stubBlobUrls();
    mockUploadRoutes();
    render(<MobileCapturePage taskId="task_001" token="token_001" />);
    const file = new File(['png'], 'page-1.png', { type: 'image/png' });

    await userEvent.upload(screen.getByLabelText('拍照/选择图片'), file);

    expect(await screen.findByText('第 1 页')).toBeTruthy();
    expect(screen.getByText('page-1.png')).toBeTruthy();
    expect(screen.queryByText('四边形框选')).toBeNull();
    expect(screen.queryByText('重新框选')).toBeNull();
    expect(screen.queryByText('拖拽')).toBeNull();
  });

  it('disables finish until at least one image uploaded', () => {
    render(<MobileCapturePage taskId="task_001" token="token_001" />);

    expect((screen.getByRole('button', { name: '完成上传' }) as HTMLButtonElement).disabled).toBe(true);
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
});
