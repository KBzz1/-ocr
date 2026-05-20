import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { http, HttpResponse } from 'msw';
import { describe, expect, it } from 'vitest';

import { server } from '../../../tests/setupTests';
import { ReviewPage } from './ReviewPage';

function mockReviewRoutes() {
  server.use(
    http.get('*/api/tasks/task_001/review', () =>
      HttpResponse.json({
        success: true,
        data: {
          task_id: 'task_001',
          status: 'review',
          review_result: {
            ocr_text: '第一页文本\n第二页文本',
            pages: [
              {
                page_id: 'page_001',
                page_no: 1,
                preview_url: '/api/tasks/task_001/images/page_001',
                parsed_text: '第一页文本'
              },
              {
                page_id: 'page_002',
                page_no: 2,
                preview_url: '/api/tasks/task_001/images/page_002',
                parsed_text: '第二页文本'
              }
            ],
            fields: [
              {
                field_key: 'patient_name',
                label: '姓名',
                value: '张三',
                status: 'unreviewed',
                evidence: [{ page_id: 'page_001', page_no: 1, text: '张三' }]
              },
              {
                field_key: 'chief_complaint',
                label: '主诉',
                value: '头痛三天',
                status: 'unreviewed',
                evidence: [{ page_id: 'page_002', page_no: 2, text: '头痛三天' }]
              }
            ]
          }
        }
      })
    ),
    http.put('*/api/tasks/task_001/review', async ({ request }) => {
      const body = await request.json() as { fields: Array<Record<string, unknown>> };
      expect(body).toMatchObject({
        fields: expect.arrayContaining([
          expect.objectContaining({ field_key: 'patient_name' })
        ])
      });
      return HttpResponse.json({
        success: true,
        data: {
          task_id: 'task_001',
          status: 'review',
          review_result: {
            ocr_text: '第一页文本\n第二页文本',
            pages: [
              {
                page_id: 'page_001',
                page_no: 1,
                preview_url: '/api/tasks/task_001/images/page_001',
                parsed_text: '第一页文本'
              },
              {
                page_id: 'page_002',
                page_no: 2,
                preview_url: '/api/tasks/task_001/images/page_002',
                parsed_text: '第二页文本'
              }
            ],
            fields: body.fields
          }
        }
      });
    }),
    http.post('*/api/tasks/task_001/complete', () =>
      HttpResponse.json({
        success: true,
        data: {
          task_id: 'task_001',
          status: 'done',
          created_at: '2026-05-19T10:00:00+08:00',
          page_count: 1
        }
      })
    )
  );
}

describe('ReviewPage', () => {
  it('uses the shared workstation navigation shell', async () => {
    mockReviewRoutes();
    render(<ReviewPage taskId="task_001" />);

    expect(await screen.findByRole('navigation', { name: '主要模块' })).toBeTruthy();
    expect(screen.getByRole('link', { name: /工作台总览/ }).getAttribute('href')).toBe('/');
    expect(screen.getByRole('link', { name: /任务管理/ }).getAttribute('href')).toBe('/tasks');
    expect(screen.getByRole('link', { name: /人工审核/ }).getAttribute('aria-current')).toBe('page');
  });

  it('shows one current page image and switches pages without rendering all images', async () => {
    mockReviewRoutes();
    render(<ReviewPage taskId="task_001" />);

    expect(await screen.findByRole('img', { name: '第 1 页原图' })).toBeTruthy();
    expect(screen.queryByRole('img', { name: '第 2 页原图' })).toBeNull();

    await userEvent.click(screen.getByRole('button', { name: '第 2 页' }));

    expect(screen.getByRole('img', { name: '第 2 页原图' })).toBeTruthy();
    expect(screen.queryByRole('img', { name: '第 1 页原图' })).toBeNull();
  });

  it('keeps OCR hidden by default and shows current page OCR on demand', async () => {
    mockReviewRoutes();
    render(<ReviewPage taskId="task_001" />);

    await screen.findByText('结构化字段');
    expect(screen.queryByText('第一页文本')).toBeNull();

    await userEvent.click(screen.getByRole('button', { name: '显示 OCR' }));
    expect(screen.getByText('第一页文本')).toBeTruthy();

    await userEvent.click(screen.getByRole('button', { name: '第 2 页' }));
    expect(screen.getByText('第二页文本')).toBeTruthy();
    expect(screen.queryByText('第一页文本')).toBeNull();

    await userEvent.click(screen.getByRole('button', { name: '隐藏 OCR' }));
    expect(screen.queryByText('第二页文本')).toBeNull();
  });

  it('shows images, OCR text, editable fields, complete and export actions', async () => {
    mockReviewRoutes();
    render(<ReviewPage taskId="task_001" />);

    expect(await screen.findByText('OCR 文本')).toBeTruthy();
    const field = screen.getByLabelText('patient_name') as HTMLInputElement;
    expect(field.value).toBe('张三');

    await userEvent.clear(field);
    await userEvent.type(field, '李四');
    await userEvent.click(screen.getByRole('button', { name: '保存审核结果' }));

    expect(await screen.findByText('已保存')).toBeTruthy();
    await userEvent.click(screen.getByRole('button', { name: '标记完成' }));
    expect(await screen.findByText('已完成')).toBeTruthy();
    expect((screen.getByRole('button', { name: '导出 JSON' }) as HTMLButtonElement).disabled).toBe(false);
    expect((screen.getByRole('button', { name: '导出 Excel' }) as HTMLButtonElement).disabled).toBe(false);
  });

  it('shows backend field labels and extracted candidate values', async () => {
    server.use(
      http.get('*/api/tasks/task_001/review', () =>
        HttpResponse.json({
          success: true,
          data: {
            task_id: 'task_001',
            status: 'review',
            review_result: {
              ocr_text: '主诉：头痛三天',
              pages: [],
              fields: [
                {
                  field_key: 'chief_complaint',
                  field_name: '主诉',
                  auto_value: '头痛三天',
                  final_value: '',
                  status: 'unreviewed'
                }
              ]
            }
          }
        })
      )
    );

    render(<ReviewPage taskId="task_001" />);

    expect(await screen.findByText('主诉')).toBeTruthy();
    expect(screen.getByText('候选值：头痛三天')).toBeTruthy();
    expect((screen.getByLabelText('chief_complaint') as HTMLInputElement).value).toBe('头痛三天');
  });

  it('shows a message when task completion validation fails', async () => {
    mockReviewRoutes();
    server.use(
      http.post('*/api/tasks/task_001/complete', () =>
        HttpResponse.json(
          {
            error: {
              code: 'REVIEW_NOT_COMPLETED',
              message: '仍有字段未审核',
              details: {}
            }
          },
          { status: 400 }
        )
      )
    );

    render(<ReviewPage taskId="task_001" />);

    await screen.findByText('OCR 文本');
    await userEvent.click(screen.getByRole('button', { name: '标记完成' }));

    expect(await screen.findByText('仍有字段未审核')).toBeTruthy();
  });
});
