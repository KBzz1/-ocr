import { expect, test } from '@playwright/test';

import {
  fulfillJson,
  installNetworkGate,
  mockSystemStatus
} from './helpers/mvpApi';

const tasks = [
  {
    task_id: 'task_uploading',
    display_name: '上传任务',
    status: 'uploading',
    created_at: '2026-06-09T09:40:00+08:00',
    page_count: 0,
    review_summary: { status: null, confirmed_count: 0, total_count: 0 },
    export_summary: { formats: [] },
    patient: { patient_id: 'P-A1B2C3D4', name: '张医生测试患者', deleted: false },
    document_type: 'copd_admission_record',
    document_type_label: '入院记录',
    record_date: '2026-06-09',
    record_time: '09:30',
    mobile_upload_url: 'http://127.0.0.1/mobile/upload/task_uploading?token=test'
  },
  {
    task_id: 'task_review',
    display_name: '待审核任务',
    status: 'review',
    created_at: '2026-06-09T09:30:00+08:00',
    page_count: 3,
    review_summary: { status: 'unreviewed', confirmed_count: 0, total_count: 8 },
    export_summary: { formats: [] },
    patient: { patient_id: 'P-B2C3D4E5', name: '李医生测试患者', deleted: false },
    document_type: 'copd_admission_record',
    document_type_label: '入院记录',
    record_date: '2026-06-08',
    record_time: null
  },
  {
    task_id: 'task_processing',
    display_name: '处理中任务',
    status: 'processing',
    created_at: '2026-06-09T09:20:00+08:00',
    page_count: 2,
    processing_summary: {
      stage: 'document_parsing',
      status: 'running',
      label: 'OCR 文档解析',
      progress_percent: 55
    },
    review_summary: { status: null },
    export_summary: { formats: [] },
    patient: { patient_id: 'P-C3D4E5F6', name: '王医生测试患者', deleted: false },
    document_type: 'copd_admission_record',
    document_type_label: '入院记录',
    record_date: '2026-06-07',
    record_time: '14:00'
  },
  {
    task_id: 'task_failed',
    display_name: '失败任务',
    status: 'failed',
    created_at: '2026-06-09T09:10:00+08:00',
    page_count: 1,
    review_summary: { status: null },
    export_summary: { formats: [] },
    error_code: 'ALGORITHM_MODULE_NOT_CONFIGURED',
    error_message: '图像处理模块未配置，请检查本地算法服务配置',
    patient: { patient_id: 'P-D4E5F6G7', name: '已删除测试患者', deleted: true },
    document_type: 'copd_admission_record',
    document_type_label: '入院记录',
    record_date: '2026-06-06',
    record_time: null
  },
  {
    task_id: 'task_done',
    display_name: '已完成任务',
    status: 'done',
    created_at: '2026-06-09T09:00:00+08:00',
    page_count: 5,
    review_summary: { status: 'confirmed', confirmed_count: 8, total_count: 8 },
    export_summary: { formats: ['json'] },
    patient: { patient_id: 'P-E5F6G7H8', name: '赵医生测试患者', deleted: false },
    document_type: 'copd_admission_record',
    document_type_label: '入院记录',
    record_date: '2026-06-05',
    record_time: '10:15'
  }
];

test.beforeEach(async ({ page }) => {
  await installNetworkGate(page);
  await mockSystemStatus(page);
  await page.route('**/api/tasks', async (route) => {
    await fulfillJson(route, { tasks });
  });
});

test('task table columns and actions stay aligned without horizontal scrolling', async ({ page }) => {
  await page.setViewportSize({ width: 2400, height: 1000 });
  await page.goto('/tasks');

  const table = page.getByRole('table', { name: '任务列表' });
  await expect(table).toBeVisible();
  await expect(table.locator('thead th').allTextContents()).resolves.toEqual([
    '批量导出',
    '任务名称',
    '患者姓名',
    '患者编号',
    '记录类型',
    '记录时间',
    '创建时间',
    '页数',
    '处理状态',
    '审核状态',
    '失败原因',
    '操作'
  ]);
  await expect(table.locator('thead th').evaluateAll((headers) =>
    headers.map((header) => getComputedStyle(header).textAlign)
  )).resolves.toEqual(Array(12).fill('center'));
  await expect(table.locator('tbody tr:first-child td').evaluateAll((cells) =>
    cells.map((cell) => getComputedStyle(cell).textAlign)
  )).resolves.toEqual(Array(12).fill('center'));

  const alignment = await table.evaluate((element) => {
    const headers = Array.from(element.querySelectorAll('thead th'));
    const cells = Array.from(element.querySelectorAll('tbody tr:first-child td'));
    return headers.map((header, index) => {
      const headerRect = header.getBoundingClientRect();
      const cellRect = cells[index].getBoundingClientRect();
      return {
        xDifference: Math.abs(headerRect.x - cellRect.x),
        widthDifference: Math.abs(headerRect.width - cellRect.width)
      };
    });
  });
  expect(alignment.every(({ xDifference, widthDifference }) => xDifference < 1 && widthDifference < 1)).toBe(true);

  const reviewRow = table.locator('tbody tr').filter({ hasText: '待审核任务' });
  const reviewButtonPositions = await reviewRow.locator('.task-list-actions > *').evaluateAll((elements) =>
    elements.map((element) => Math.round(element.getBoundingClientRect().x))
  );
  expect(reviewButtonPositions).toHaveLength(4);
  expect(reviewButtonPositions[1] - reviewButtonPositions[0]).toBe(59);
  expect(reviewButtonPositions[2] - reviewButtonPositions[1]).toBe(59);
  expect(reviewButtonPositions[3] - reviewButtonPositions[2]).toBe(59);

  await page.screenshot({
    path: 'output/playwright/task-table-alignment-wide.png',
    fullPage: true
  });

  await page.setViewportSize({ width: 1366, height: 900 });
  const overflow = await page.locator('.task-list-table-wrap').evaluate((element) => ({
    clientWidth: element.clientWidth,
    scrollWidth: element.scrollWidth
  }));
  expect(overflow.scrollWidth).toBeLessThanOrEqual(overflow.clientWidth);

  await page.screenshot({
    path: 'output/playwright/task-table-alignment-narrow.png',
    fullPage: true
  });
  await page.evaluate(() => window.__assertE2eNetworkGate());
});

declare global {
  interface Window {
    __assertE2eNetworkGate: () => void;
  }
}
