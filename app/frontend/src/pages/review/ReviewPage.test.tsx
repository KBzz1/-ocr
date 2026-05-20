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
            ocr_text: '姓名：张三',
            pages: [{ page_id: 'page_001', page_no: 1, preview_url: '/api/tasks/task_001/images/page_001' }],
            fields: [{ field_key: 'patient_name', label: '姓名', value: '张三', status: 'unreviewed' }]
          }
        }
      })
    ),
    http.put('*/api/tasks/task_001/review', async ({ request }) => {
      const body = await request.json();
      expect(body).toMatchObject({
        fields: [{ field_key: 'patient_name', value: '李四', status: 'modified' }]
      });
      return HttpResponse.json({
        success: true,
        data: {
          task_id: 'task_001',
          status: 'review',
          review_result: {
            ocr_text: '姓名：张三',
            pages: [{ page_id: 'page_001', page_no: 1, preview_url: '/api/tasks/task_001/images/page_001' }],
            fields: [{ field_key: 'patient_name', label: '姓名', value: '李四', status: 'modified' }]
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
