import { expect, test, type Page } from '@playwright/test';

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
      review_summary: { confirmed_count: 0, total_count: 51 },
      patient: { patient_id: 'P-A18Z3C04', name: '张三', deleted: false },
      document_type: 'qwen_batch_admission_record',
      document_type_label: '入院记录',
      record_date: '2026-06-07',
      record_time: '09:30',
      processing_summary: {
        stage: 'done',
        status: 'completed',
        label: '处理完成',
        progress_percent: 100
      }
    });
  });

  await page.route('**/api/tasks/task_001/review', async (route) => {
    if (route.request().method() === 'PUT') {
      await fulfillJson(route, {
        task_id: 'task_001',
        status: 'review',
        review_result: buildQwenV2ReviewResult(OCR_TEXT)
      });
      return;
    }
    await fulfillJson(route, {
      task_id: 'task_001',
      status: 'review',
      review_result: buildQwenV2ReviewResult(OCR_TEXT)
    });
  });

  await page.route('**/api/tasks/task_001/pages/page_1/image', async (route) => {
    await route.fulfill({ status: 200, body: '', contentType: 'image/png' });
  });
}

async function capturePatientStep(page: Page, fileName: string) {
  await page.goto('/');
  await page.getByRole('button', { name: '新建任务' }).click();
  const dialog = page.getByRole('dialog', { name: '新建任务' });
  await expect(dialog).toBeVisible();
  await dialog.getByLabel('患者姓名').fill('张三');
  await dialog.getByRole('button', { name: '搜索患者' }).click();
  await dialog.getByRole('button', { name: '选择 P-A18Z3C04' }).click();
  await page.waitForTimeout(200);
  await page.screenshot({ path: fileName, fullPage: false });
}

async function captureRecordStep(page: Page, fileName: string) {
  const dialog = page.getByRole('dialog', { name: '新建任务' });
  await dialog.locator('[data-testid="create-task-next"]').click();
  await expect(dialog.getByRole('button', { name: '下一步' })).toBeVisible();
  await page.screenshot({ path: fileName, fullPage: false });
}

async function captureOcrWindow(page: Page, fileName: string) {
  await page.goto('/tasks/task_001/review');
  await expect(page.getByLabel('主诉 字段')).toBeVisible();
  await expect(page.getByText('现病史')).toBeVisible();
  await expect(page.getByText('辅助检查')).toBeVisible();
  await page.locator('.review-ocr-open-button').first().click();
  const ocrWindow = page.locator('.review-ocr-window');
  await expect(ocrWindow).toBeVisible();
  await expect(ocrWindow).toContainText('主诉');
  await expect(ocrWindow).toContainText('OCR 原文');
  await page.waitForTimeout(150);
  await page.screenshot({ path: fileName, fullPage: false });
}

test.beforeEach(async ({ page }) => {
  await installNetworkGate(page);
  await mockSystemStatus(page);
  await installTaskApis(page);
});

for (const [label, width, height] of [
  ['1366x768', 1366, 768],
  ['1440x900', 1440, 900],
  ['1280x720', 1280, 720],
  ['1536x1024', 1536, 1024],
  ['1448x1086', 1448, 1086]
] as const) {
  test(`popup loop R1 screenshots at ${label}`, async ({ page }) => {
    await page.setViewportSize({ width, height });
    await capturePatientStep(page, `output/playwright/popup-loop-new-task-patient-${label}.png`);
    await captureRecordStep(page, `output/playwright/popup-loop-new-task-record-info-${label}.png`);
    await captureOcrWindow(page, `output/playwright/popup-loop-ocr-window-${label}.png`);
  });
}

// 默认 1366x768 视图保留旧文件名以保持向后兼容
test('popup loop R1 screenshots: default 1366x768 (canonical names)', async ({ page }) => {
  await page.setViewportSize({ width: 1366, height: 768 });
  await capturePatientStep(page, 'output/playwright/popup-loop-new-task-patient.png');
  await captureRecordStep(page, 'output/playwright/popup-loop-new-task-record-info.png');
  await captureOcrWindow(page, 'output/playwright/popup-loop-ocr-window.png');
});

test('popup loop: search button disabled / hover / focus states', async ({ page }) => {
  await page.setViewportSize({ width: 1366, height: 768 });
  await page.goto('/');
  await page.getByRole('button', { name: '新建任务' }).click();
  const dialog = page.getByRole('dialog', { name: '新建任务' });
  await expect(dialog).toBeVisible();

  // 1. 搜索按钮 disabled 状态：姓名为空
  const searchButton = dialog.getByRole('button', { name: '搜索患者' });
  await expect(searchButton).toBeDisabled();
  await page.screenshot({ path: 'output/playwright/popup-loop-search-button-disabled.png', fullPage: false });

  // 2. 搜索按钮 default 状态：填入姓名但未点击
  await dialog.getByLabel('患者姓名').fill('张三');
  await expect(searchButton).toBeEnabled();
  await page.screenshot({ path: 'output/playwright/popup-loop-search-button-default.png', fullPage: false });

  // 3. 搜索按钮 hover 状态
  await searchButton.hover();
  await page.waitForTimeout(120);
  await page.screenshot({ path: 'output/playwright/popup-loop-search-button-hover.png', fullPage: false });

  // 4. 搜索按钮 focus 状态
  await searchButton.focus();
  await page.screenshot({ path: 'output/playwright/popup-loop-search-button-focus.png', fullPage: false });
});
