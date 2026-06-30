import { act, render, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { http, HttpResponse } from 'msw';
import { afterEach, describe, expect, it, vi } from 'vitest';

import type { CreateTaskInput } from '../../api/tasks';
import { server } from '../../../tests/setupTests';
import { CreateTaskDialog } from './CreateTaskDialog';

afterEach(() => {
  vi.useRealTimers();
});

function mockPatientsSearch(
  patients: Array<{ patient_id: string; name: string; gender?: string | null; age?: number | null; task_count?: number; latest_record_at?: string | null }>
) {
  return http.get('*/api/patients', () =>
    HttpResponse.json({
      success: true,
      data: {
        patients: patients.map((patient) => ({
          patient_id: patient.patient_id,
          name: patient.name,
          gender: patient.gender ?? null,
          age: patient.age ?? null,
          created_at: '2026-06-07T10:00:00+08:00',
          updated_at: '2026-06-07T10:00:00+08:00',
          deleted_at: null,
          task_count: patient.task_count ?? 0,
          latest_record_at: patient.latest_record_at ?? null
        }))
      }
    })
  );
}

describe('CreateTaskDialog', () => {
  it('提交完整 payload 创建任务', async () => {
    const user = userEvent.setup();
    let createBody: CreateTaskInput | null = null;
    server.use(
      mockPatientsSearch([{ patient_id: 'P-A1B2C3D4', name: '测试用例', task_count: 2, latest_record_at: '2026-06-05' }]),
      http.post('*/api/tasks', async ({ request }) => {
        createBody = (await request.json()) as CreateTaskInput;
        return HttpResponse.json({
          success: true,
          data: {
            task_id: '1',
            display_name: '1',
            status: 'uploading',
            upload_token: 'token_001',
            mobile_upload_url: 'http://127.0.0.1:8081/mobile/upload/1?token=token_001',
            patient: { patient_id: 'P-A1B2C3D4', name: '测试用例', deleted: false },
            document_type: 'copd_admission_record',
            document_type_label: '入院记录',
            record_date: '2026-06-07',
            record_time: '09:30'
          }
        });
      })
    );

    const handleSubmit = vi.fn(async (input: CreateTaskInput) => {
      const response = await fetch('/api/tasks', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(input)
      });
      await response.json();
    });

    render(
      <CreateTaskDialog
        isOpen={true}
        isSubmitting={false}
        onClose={() => undefined}
        onSubmit={handleSubmit}
      />
    );

    const dialog = await screen.findByRole('dialog', { name: '新建任务' });
    await user.type(within(dialog).getByLabelText('患者姓名'), '测试用例');
    await user.click(within(dialog).getByRole('button', { name: '搜索患者' }));

    const existingPatientButton = await within(dialog).findByRole('button', {
      name: /选择.*P-A1B2C3D4/
    });
    await user.click(existingPatientButton);
    await user.click(within(dialog).getByRole('button', { name: '下一步' }));

    const recordTypeSelect = within(dialog).getByLabelText('记录类型') as HTMLSelectElement;
    await user.selectOptions(recordTypeSelect, 'copd_admission_record');

    await user.clear(within(dialog).getByLabelText('记录日期'));
    await user.type(within(dialog).getByLabelText('记录日期'), '2026-06-07');

    await user.clear(within(dialog).getByLabelText('记录时间（可选）'));
    await user.type(within(dialog).getByLabelText('记录时间（可选）'), '09:30');

    await user.click(within(dialog).getByRole('button', { name: '下一步' }));

    await waitFor(() => {
      expect(handleSubmit).toHaveBeenCalledTimes(1);
    });
    expect(createBody).toEqual({
      patient_id: 'P-A1B2C3D4',
      document_type: 'copd_admission_record',
      record_date: '2026-06-07',
      record_time: '09:30'
    });
  });

  it('精确同名时仅在点击"仍然新建"后才创建患者', async () => {
    const user = userEvent.setup();
    let createPatientCount = 0;
    server.use(
      mockPatientsSearch([
        { patient_id: 'P-A1B2C3D4', name: '测试用例', task_count: 1, latest_record_at: '2026-06-05' },
        { patient_id: 'P-E5F6A7B8', name: '测试用例', task_count: 3, latest_record_at: '2026-05-30' }
      ]),
      http.post('*/api/patients', async () => {
        createPatientCount += 1;
        return HttpResponse.json({
          success: true,
          data: {
            patient_id: 'P-NEWPAT99',
            name: '测试用例',
            created_at: '2026-06-07T10:00:00+08:00',
            updated_at: '2026-06-07T10:00:00+08:00',
            deleted_at: null
          }
        });
      })
    );

    render(
      <CreateTaskDialog
        isOpen={true}
        isSubmitting={false}
        onClose={() => undefined}
        onSubmit={async () => undefined}
      />
    );

    const dialog = await screen.findByRole('dialog', { name: '新建任务' });
    await user.type(within(dialog).getByLabelText('患者姓名'), '测试用例');
    await user.click(within(dialog).getByRole('button', { name: '搜索患者' }));

    expect(await within(dialog).findByText('P-A1B2C3D4')).toBeTruthy();
    expect(within(dialog).getByText('P-E5F6A7B8')).toBeTruthy();
    expect(createPatientCount).toBe(0);

    await user.click(within(dialog).getByRole('button', { name: '仍然新建患者' }));

    await waitFor(() => {
      expect(createPatientCount).toBe(1);
    });

    expect(await within(dialog).findByText('P-NEWPAT99')).toBeTruthy();
  });

  it('提交期间不显示二维码', async () => {
    const user = userEvent.setup();
    let resolveCreate: ((value: unknown) => void) | null = null;
    const createPromise = new Promise((resolve) => {
      resolveCreate = resolve;
    });
    server.use(
      mockPatientsSearch([{ patient_id: 'P-A1B2C3D4', name: '测试用例' }])
    );

    const handleSubmit = vi.fn(async (_input: CreateTaskInput) => {
      await createPromise;
    });

    function Host() {
      return (
        <>
          <CreateTaskDialog
            isOpen={true}
            isSubmitting={false}
            onClose={() => undefined}
            onSubmit={handleSubmit}
          />
        </>
      );
    }

    render(<Host />);

    const dialog = await screen.findByRole('dialog', { name: '新建任务' });
    await user.type(within(dialog).getByLabelText('患者姓名'), '测试用例');
    await user.click(within(dialog).getByRole('button', { name: '搜索患者' }));
    const existingPatientButton = await within(dialog).findByRole('button', {
      name: /选择.*P-A1B2C3D4/
    });
    await user.click(existingPatientButton);
    await user.click(within(dialog).getByRole('button', { name: '下一步' }));

    const recordTypeSelect = within(dialog).getByLabelText('记录类型') as HTMLSelectElement;
    await user.selectOptions(recordTypeSelect, 'copd_admission_record');

    await user.clear(within(dialog).getByLabelText('记录日期'));
    await user.type(within(dialog).getByLabelText('记录日期'), '2026-06-07');

    await user.click(within(dialog).getByRole('button', { name: '下一步' }));

    // 响应未返回前，弹窗内不应出现二维码相关内容
    expect(screen.queryByRole('dialog', { name: '手机扫码上传' })).toBeNull();
    expect(screen.queryByRole('img', { name: '任务上传二维码' })).toBeNull();
    expect(within(dialog).queryByRole('img', { name: '任务上传二维码' })).toBeNull();

    await act(async () => {
      resolveCreate?.({});
    });

    await waitFor(() => {
      expect(handleSubmit).toHaveBeenCalledTimes(1);
    });
  });
});
