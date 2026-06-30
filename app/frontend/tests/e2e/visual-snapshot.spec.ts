import { test, expect, type Page } from '@playwright/test';

import {
  fulfillJson,
  installNetworkGate,
  mockSystemStatus
} from './helpers/mvpApi';
import { buildQwenV2ReviewResult } from '../fixtures/qwenReview';

const OCR_TEXT = `姓名：张三  性别：男  年龄：56岁  科别：呼吸与危重症医学科  床号：12
入院日期：2024年05月10日 09时30分
记录日期：2024年05月10日 09时15分

反复咳嗽、咳痰20年，加重3天，加重10天。

现病史：患者20年前受凉后出现咳嗽、咳痰，痰为白色泡沫样，易咳出，伴活动后气促，多次于当地医院就诊，诊断为「慢性支气管炎」，给予抗感染、止咳化痰等治疗后好转出院（具体诊疗经过不详）。10余天前受凉后再次出现咳嗽、咳痰，痰量较前增多，为黄色脓痰，伴发热，体温最高38.5℃，
无畏寒、寒战，伴活动后气促，休息后可缓解，无胸痛、咯血，无夜间阵发性呼吸困难，无双下肢水肿。曾自行口服「头孢克肟、阿莫西林」等药物，症状无明显缓解，遂来我院就诊，门诊以「慢性阻塞性肺疾病急性加重期」收入院。

既往史：高血压病5年，最高血压160/100mmHg，长期口服「缬沙坦氢氯噻嗪」控制，血压控制可。
否认糖尿病史。否认肝炎、结核等传染病史。否认手术外伤史。否认输血史。否认食物及药物过敏史。

个人史：吸烟30年，约20支/日，已戒烟1年。否认饮酒史。否认工业毒物及放射性物质接触史。
婚育史：已婚，配偶体健，育有一子一女。

家族史：父母已故，否认家族性遗传病史。`;

async function installTaskApis(page: Page) {
  await page.route(/\/api\/patients(?:\?.*)?$/, async (route) => {
    await fulfillJson(route, {
      patients: [
        {
          patient_id: 'P-A18Z3C04',
          name: '张三',
          gender: '男',
          age: 58,
          task_count: 2,
          latest_record_at: '2026-06-07'
        },
        {
          patient_id: 'P-B5B2C3D7',
          name: '张三',
          gender: '男',
          age: 54,
          task_count: 1,
          latest_record_at: '2025-08-21'
        }
      ]
    });
  });
  await page.route('**/api/tasks', async (route) => {
    if (route.request().method() === 'POST') {
      await fulfillJson(route, {
        task_id: 'task_001',
        display_name: 'Qwen真实烟测审核',
        status: 'uploading',
        upload_token: 'token_001',
        mobile_upload_url: 'http://127.0.0.1:8081/mobile/upload/task_001?token=token_001',
        patient: { patient_id: 'P-A18Z3C04', name: '张三', deleted: false },
        document_type: 'qwen_batch_admission_record',
        document_type_label: '入院记录',
        record_date: '2026-06-07',
        record_time: '09:30'
      });
      return;
    }
    await fulfillJson(route, { tasks: [] });
  });
  await page.route('**/api/tasks/task_001', async (route) => {
    await fulfillJson(route, {
      task_id: 'task_001',
      display_name: 'Qwen真实烟测审核',
      status: 'review',
      created_at: '2026-05-19T10:00:00+08:00',
      updated_at: '2026-05-19T10:03:00+08:00',
      page_count: 1,
      processing_summary: { stage: 'done', status: 'completed', label: '处理完成', progress_percent: 100 },
      review_summary: { confirmed_count: 0, total_count: 51 },
      patient: { patient_id: 'P-A18Z3C04', name: '张三', deleted: false },
      document_type: 'qwen_batch_admission_record',
      document_type_label: '入院记录',
      record_date: '2026-06-07',
      record_time: '09:30',
      images: [{
        page_id: 'page_001',
        page_no: 1,
        image_url: 'data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNkYAAAAAYAAjCB0C8AAAAASUVORK5CYII=',
        preview_url: 'data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNkYAAAAAYAAjCB0C8AAAAASUVORK5CYII='
      }],
      review_result: buildQwenV2ReviewResult(OCR_TEXT)
    });
  });
  await page.route('**/api/tasks/task_001/review', async (route) => {
    await fulfillJson(route, {
      task_id: 'task_001',
      status: 'review',
      review_result: {
        ...buildQwenV2ReviewResult(OCR_TEXT)
      }
    });
  });
}

test.describe('Visual baseline: design-aligned popups', () => {
  test.beforeEach(async ({ page }) => {
    await installNetworkGate(page);
    await mockSystemStatus(page);
    await installTaskApis(page);
  });

  test('选患者 dialog matches design', async ({ page }) => {
    await page.setViewportSize({ width: 1536, height: 1024 });
    await page.goto('/');
    await page.getByRole('button', { name: '新建任务' }).click();
    const dialog = page.getByRole('dialog', { name: '新建任务' });
    await expect(dialog).toBeVisible();
    await dialog.getByLabel('患者姓名').fill('张三');
    await dialog.getByRole('button', { name: '搜索患者' }).click();
    await dialog.getByRole('button', { name: '选择 P-A18Z3C04' }).click();
    await page.waitForTimeout(200);
    await expect(page).toHaveScreenshot('popup-patient-baseline.png', {
      maxDiffPixels: 0
    });
  });

  test('记录信息 dialog matches design', async ({ page }) => {
    await page.setViewportSize({ width: 1536, height: 1024 });
    await page.goto('/');
    await page.getByRole('button', { name: '新建任务' }).click();
    const dialog = page.getByRole('dialog', { name: '新建任务' });
    await expect(dialog).toBeVisible();
    await dialog.getByLabel('患者姓名').fill('张三');
    await dialog.getByRole('button', { name: '搜索患者' }).click();
    await dialog.getByRole('button', { name: '选择 P-A18Z3C04' }).click();
    await dialog.getByRole('button', { name: '下一步' }).click();
    await page.waitForTimeout(200);
    await expect(page).toHaveScreenshot('popup-record-baseline.png', {
      maxDiffPixels: 0
    });
  });

  test('OCR 浮窗 matches design', async ({ page }) => {
    await page.setViewportSize({ width: 1448, height: 1086 });
    await page.goto('/tasks/task_001/review');
    await page.getByRole('button', { name: '打开 OCR' }).click();
    const ocr = page.getByRole('dialog', { name: '主诉 · OCR 原文' });
    await expect(ocr).toBeVisible();
    await page.waitForTimeout(200);
    await expect(page).toHaveScreenshot('popup-ocr-baseline.png', {
      maxDiffPixels: 0
    });
  });
});
