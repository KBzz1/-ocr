import { expect, test } from '@playwright/test';

import {
  fulfillError,
  fulfillJson,
  installNetworkGate,
  mockSystemStatus
} from './helpers/mvpApi';

const imageFixture = 'src/assets/logos/xinqiao-hospital-logo.jpg';

test.beforeEach(async ({ page }) => {
  await installNetworkGate(page);
});

test('MVP flow: create task, upload images, finish, review, done, export', async ({ page }) => {
  let uploadedPages = 0;

  await mockSystemStatus(page);
  await page.route('**/api/tasks', async (route) => {
    if (route.request().method() === 'POST') {
      await fulfillJson(route, {
        task_id: 'task_001',
        status: 'uploading',
        upload_token: 'token_001',
        mobile_upload_url: 'http://127.0.0.1:8081/mobile/upload/task_001?token=token_001'
      });
      return;
    }
    await fulfillJson(route, { tasks: [] });
  });
  await page.route('**/api/mobile-upload/task_001/images?token=token_001', async (route) => {
    uploadedPages += 1;
    await fulfillJson(route, {
      page_id: `page_${uploadedPages}`,
      task_id: 'task_001',
      page_no: uploadedPages,
      uploaded_at: '2026-05-19T10:00:00+08:00'
    }, 201);
  });
  await page.route('**/api/mobile-upload/task_001/finish?token=token_001', async (route) => {
    await fulfillJson(route, { task_id: 'task_001', status: 'processing', created_at: '2026-05-19T10:00:00+08:00', page_count: uploadedPages });
  });
  await page.route('**/api/tasks/task_001/pages/*/image', async (route) => {
    await route.fulfill({ status: 200, body: '', contentType: 'image/png' });
  });
  await page.route('**/api/tasks/task_001/review', async (route) => {
    if (route.request().method() === 'PUT') {
      await fulfillJson(route, {
        task_id: 'task_001',
        status: 'review',
        review_result: {
          ocr_text: '姓名：张三',
          fields: [{ field_key: 'patient_name', label: '姓名', value: '李四', status: 'modified' }],
          pages: [{ page_id: 'page_1', page_no: 1 }]
        }
      });
      return;
    }
    await fulfillJson(route, {
      task_id: 'task_001',
      status: 'review',
      review_result: {
        ocr_text: '模拟 OCR 文本：姓名 张三',
        fields: [
          {
            field_key: 'patient_name',
            label: '姓名',
            value: '张三',
            candidate_value: '张三',
            auto_value: '张三',
            final_value: '张三',
            status: 'unreviewed',
            evidence: [{ page_no: 1, text: 'fixture evidence' }]
          }
        ],
        pages: [{ page_id: 'page_1', page_no: 1, preview_url: '/api/tasks/task_001/pages/page_1/image' }]
      }
    });
  });
  await page.route('**/api/tasks/task_001/complete', async (route) => {
    await fulfillJson(route, { task_id: 'task_001', status: 'done', created_at: '2026-05-19T10:00:00+08:00', page_count: 3 });
  });
  await page.route('**/api/tasks/task_001/export/json', async (route) => {
    await route.fulfill({ body: '{}', headers: { 'content-type': 'application/json' } });
  });
  await page.route('**/api/tasks/task_001/export/excel', async (route) => {
    await route.fulfill({ body: 'excel', headers: { 'content-type': 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet' } });
  });

  await page.goto('/');
  await page.getByRole('button', { name: '新建任务' }).click();
  await expect(page.getByText('task_001', { exact: true })).toBeVisible();
  await expect(page.getByText('http://127.0.0.1:8081/mobile/upload/task_001?token=token_001')).toBeVisible();

  await page.goto('/mobile/upload/task_001?token=token_001');
  await page.getByLabel('拍照/选择图片').setInputFiles([imageFixture, imageFixture, imageFixture]);
  await expect(page.getByText('第 1 页')).toBeVisible();
  await expect(page.getByText('第 3 页')).toBeVisible();
  await page.getByRole('button', { name: '完成上传' }).click();
  await expect(page.getByText('上传已完成，请回到电脑端查看处理结果')).toBeVisible();

  await page.goto('/tasks/task_001/review');
  await page.getByLabel('patient_name').fill('李四');
  await page.getByRole('button', { name: '保存审核结果' }).click();
  await page.getByRole('button', { name: '标记完成' }).click();
  await expect(page.getByText('已完成')).toBeVisible();
  await expect(page.getByRole('button', { name: '导出 JSON' })).toBeEnabled();
  await expect(page.getByRole('button', { name: '导出 Excel' })).toBeEnabled();
  await page.evaluate(() => window.__assertE2eNetworkGate());
});

declare global {
  interface Window {
    __assertE2eNetworkGate: () => void;
  }
}
