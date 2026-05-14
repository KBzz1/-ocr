import { render, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { http, HttpResponse } from 'msw';
import { describe, expect, it, vi } from 'vitest';

import { server } from '../../../tests/setupTests';
import {
  completeReviewFixture,
  failedReviewTaskDetail,
  mockReviewResultData,
  mockReviewTaskDetail,
  readyReviewTaskDetail,
  reviewFixture
} from '../../../tests/fixtures/review';
import { ReviewPlaceholder } from './ReviewPlaceholder';

function renderReview(taskId = 'task-ready') {
  return render(<ReviewPlaceholder taskId={taskId} />);
}

function expectPresent(element: HTMLElement | null) {
  expect(element).not.toBeNull();
}

describe('ReviewPlaceholder', () => {
  it('displays original image, parsed text and backend structured fields', async () => {
    server.use(mockReviewTaskDetail(), mockReviewResultData());

    renderReview();

    expectPresent(await screen.findByRole('region', { name: '原图' }));
    expectPresent(screen.getByRole('region', { name: '解析文本' }));
    expectPresent(screen.getByRole('region', { name: '结构化字段' }));
    expect(screen.getByRole('img', { name: '第1页原图' }).getAttribute('src')).toBe(
      '/api/tasks/task-ready/pages/page-001/image'
    );
    expectPresent(screen.getByText('第1页解析文本：主诉 头痛三天'));
    expect((screen.getByRole('textbox', { name: '主诉' }) as HTMLTextAreaElement).value).toBe('');
    expect(screen.queryByText('schema 自动字段')).toBeNull();
  });

  it('switches pages using backend page order and can view merged text', async () => {
    const user = userEvent.setup();
    server.use(mockReviewTaskDetail(), mockReviewResultData());

    renderReview();

    await user.click(await screen.findByRole('button', { name: '第2页' }));

    expect(screen.getByRole('img', { name: '第2页原图' }).getAttribute('src')).toBe(
      '/api/tasks/task-ready/pages/page-002/image'
    );
    expectPresent(screen.getByText('第2页解析文本：既往史 无特殊'));

    await user.click(screen.getByRole('button', { name: '合并文本' }));

    expectPresent(screen.getByText(/第1页解析文本：主诉 头痛三天/));
    expectPresent(screen.getByText(/第2页解析文本：既往史 无特殊/));
  });

  it('saves edited fields without overwriting candidate values', async () => {
    const user = userEvent.setup();
    const saveSpy = vi.fn();
    server.use(
      mockReviewTaskDetail(),
      mockReviewResultData(),
      http.put('*/api/tasks/task-ready/review/fields/chief_complaint', async ({ request }) => {
        saveSpy(await request.json());
        return HttpResponse.json({
          success: true,
          data: {
            field_key: 'chief_complaint',
            final_value: '头痛四天',
            status: 'modified'
          }
        });
      })
    );

    renderReview();

    const field = await screen.findByRole('textbox', { name: '主诉' });
    await user.clear(field);
    await user.type(field, '头痛四天');
    await user.tab();

    await waitFor(() =>
      expect(saveSpy).toHaveBeenCalledWith({ final_value: '头痛四天', status: 'modified' })
    );
    expectPresent(screen.getByText('候选值：头痛三天'));
    expectPresent(screen.getByText('已修改'));
  });

  it('shows evidence, missing evidence and unavailable source page states', async () => {
    const user = userEvent.setup();
    const reviewWithEvidenceStates = {
      ...completeReviewFixture,
      fields: [
        completeReviewFixture.fields[0],
        completeReviewFixture.fields[1],
        {
          field_key: 'discharge_note',
          label: '出院记录',
          candidate_value: '需复查',
          final_value: '需复查',
          status: 'confirmed',
          evidence: [{ page_id: 'missing', page_no: 99, text: '需复查' }]
        }
      ]
    };
    server.use(mockReviewTaskDetail(), mockReviewResultData(reviewWithEvidenceStates));

    renderReview();

    expectPresent(await screen.findByText('来源：第1页 头痛三天'));
    expectPresent(screen.getByText('未定位来源'));
    expectPresent(screen.getByText('需人工确认'));

    await user.click(screen.getByRole('button', { name: '查看主诉来源' }));
    expectPresent(screen.getByText('已定位来源：第1页 头痛三天'));

    await user.click(screen.getByRole('button', { name: '查看既往史来源' }));
    expectPresent(screen.getByText('此字段无对应来源文本'));

    await user.click(screen.getByRole('button', { name: '查看出院记录来源' }));
    expectPresent(screen.getByText('来源页不可用'));
  });

  it('blocks confirmation when local summary still has unresolved fields', async () => {
    const user = userEvent.setup();
    const confirmSpy = vi.fn();
    server.use(
      mockReviewTaskDetail(),
      mockReviewResultData(reviewFixture),
      http.post('*/api/tasks/task-ready/review/confirm', () => {
        confirmSpy();
        return HttpResponse.json({ success: true, data: { task_id: 'task-ready', status: 'confirmed' } });
      })
    );

    renderReview();

    await user.click(await screen.findByRole('button', { name: '确认审核' }));

    expect(confirmSpy).not.toHaveBeenCalled();
    expect(screen.getByRole('alert').textContent).toContain('仍有 1 个未审核字段');
  });

  it('confirms review when all fields are confirmed or modified', async () => {
    const user = userEvent.setup();
    const confirmSpy = vi.fn();
    server.use(
      mockReviewTaskDetail(),
      mockReviewResultData(completeReviewFixture),
      http.post('*/api/tasks/task-ready/review/confirm', () => {
        confirmSpy();
        return HttpResponse.json({ success: true, data: { task_id: 'task-ready', status: 'confirmed' } });
      })
    );

    renderReview();

    await user.click(await screen.findByRole('button', { name: '确认审核' }));

    await waitFor(() => expect(confirmSpy).toHaveBeenCalledTimes(1));
    expectPresent(screen.getByText('审核已确认'));
  });

  it('prevents failed tasks from entering normal review and exposes retry action', async () => {
    server.use(mockReviewTaskDetail(failedReviewTaskDetail));

    renderReview('task-failed');

    const alert = await screen.findByRole('alert');
    expect(alert.textContent).toContain('图像处理模块未配置');
    expectPresent(within(alert).getByRole('button', { name: '重新处理' }));
    expect(screen.queryByRole('region', { name: '结构化字段' })).toBeNull();
  });
});
