import { expect, test } from '@playwright/test';

import {
  fulfillError,
  fulfillJson,
  installNetworkGate,
  mockSystemStatus
} from './helpers/mvpApi';

const patientId = 'P-A1B2C3D4';
const taskId = 'task_001';

test.beforeEach(async ({ page }) => {
  await installNetworkGate(page);
});

test('patient records: create patient, create task, view detail, delete patient keeps task', async ({ page }) => {
  await mockSystemStatus(page);
  let taskCreated = false;
  let patientDeleted = false;

  // 患者列表 / 创建患者
  await page.route(/\/api\/patients(?:\?.*)?$/, async (route) => {
    if (route.request().method() === 'POST') {
      await fulfillJson(
        route,
        {
          patient_id: patientId,
          name: '测试用例',
          created_at: '2026-06-07T10:00:00+08:00',
          updated_at: '2026-06-07T10:00:00+08:00',
          deleted_at: null
        },
        201
      );
      return;
    }
    await fulfillJson(route, {
      patients: [
        {
          patient_id: patientId,
          name: '测试用例',
          task_count: 1,
          latest_record_at: '2026-06-07'
        }
      ]
    });
  });

  // 创建任务
  await page.route('**/api/tasks', async (route) => {
    if (route.request().method() === 'POST') {
      const body = JSON.parse(route.request().postData() || '{}');
      expect(body.patient_id).toBe(patientId);
      expect(body.document_type).toBe('copd_admission_record');
      expect(body.record_date).toBe('2026-06-07');
      taskCreated = true;
      await fulfillJson(
        route,
        {
          task_id: taskId,
          display_name: taskId,
          status: 'uploading',
          upload_token: 'token_001',
          mobile_upload_url: 'http://127.0.0.1:8081/mobile/upload/task_001?token=token_001',
          patient: { patient_id: patientId, name: '测试用例', deleted: false },
          document_type: 'copd_admission_record',
          document_type_label: '入院记录',
          record_date: '2026-06-07',
          record_time: null
        },
        201
      );
      return;
    }
    await fulfillJson(route, {
      tasks: taskCreated
        ? [
            {
              task_id: taskId,
              display_name: taskId,
              status: 'review',
              created_at: '2026-06-07T10:00:00+08:00',
              updated_at: '2026-06-07T11:00:00+08:00',
              page_count: 1,
              document_type: 'copd_admission_record',
              document_type_label: '入院记录',
              record_date: '2026-06-07',
              record_time: null,
              patient: { patient_id: patientId, name: '测试用例', deleted: patientDeleted }
            }
          ]
        : []
    });
  });

  // 患者详情
  await page.route(`**/api/patients/${patientId}/records`, async (route) => {
    await fulfillJson(route, {
      patient: {
        patient_id: patientId,
        name: '测试用例',
        created_at: '2026-06-07T10:00:00+08:00',
        updated_at: '2026-06-07T10:00:00+08:00',
        deleted_at: null
      },
      record_groups: [
        {
          document_type: 'copd_admission_record',
          document_type_label: '入院记录',
          tasks: [
            {
              task_id: taskId,
              status: 'review',
              created_at: '2026-06-07T10:00:00+08:00',
              updated_at: '2026-06-07T11:00:00+08:00',
              page_count: 1,
              document_type: 'copd_admission_record',
              document_type_label: '入院记录',
              record_date: '2026-06-07',
              record_time: null,
              patient: { patient_id: patientId, name: '测试用例', deleted: false }
            }
          ]
        }
      ]
    });
  });

  // 删除患者 (仅删除)
  await page.route(`**/api/patients/${patientId}**`, async (route) => {
    if (route.request().method() === 'DELETE') {
      patientDeleted = true;
      await fulfillJson(route, {
        patient_id: patientId,
        deleted: true,
        deleted_task_ids: []
      });
      return;
    }
    await route.continue();
  });

  // 1. 工作台首页 -> 点击新建任务
  await page.goto('/');
  await expect(page.getByRole('button', { name: '新建任务' })).toBeVisible();
  await page.getByRole('button', { name: '新建任务' }).click();

  // 2. 在弹窗内填入患者姓名
  await expect(page.getByRole('dialog', { name: '新建任务' })).toBeVisible();
  const nameInput = page.getByLabel('患者姓名');
  await nameInput.fill('测试用例');
  await page.getByRole('button', { name: '搜索患者' }).click();

  // 3. 选择已有患者
  await page.getByRole('button', { name: `选择 ${patientId}` }).click();

  // 4. 选择记录类型/日期
  await page.getByLabel('记录类型').selectOption('copd_admission_record');
  await page.getByLabel('记录日期').fill('2026-06-07');

  // 5. 提交
  await page.getByRole('button', { name: '创建任务' }).click();

  // 6. 二维码出现
  await expect(page.getByRole('dialog', { name: '任务上传二维码' })).toBeVisible();

  // 7. 导航到患者管理
  await page.goto('/patients');
  await expect(page.getByText('测试用例')).toBeVisible();

  // 8. 导航到患者详情
  await page.goto(`/patients/${patientId}`);
  await expect(page.getByText('入院记录')).toBeVisible();

  // 9. 删除患者 (仅删除)
  await page.getByRole('button', { name: '删除患者' }).click();
  await expect(page.getByRole('dialog', { name: '删除患者' })).toBeVisible();
  await page.getByRole('button', { name: '仅删除患者' }).click();

  // 10. 任务管理应仍能看到该任务且标记患者已删除
  await page.goto('/tasks');
  await expect(page.getByText('测试用例')).toBeVisible();
  await expect(page.getByText('患者已删除')).toBeVisible();
});
