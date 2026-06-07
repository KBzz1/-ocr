import { render, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { http, HttpResponse } from 'msw';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import { server } from '../../../tests/setupTests';
import { PatientDetailPage } from './PatientDetailPage';

const patientId = 'P-A1B2C3D4';

const patientRecord = {
  patient_id: patientId,
  name: '测试用例',
  created_at: '2026-06-07T10:00:00+08:00',
  updated_at: '2026-06-07T10:00:00+08:00',
  deleted_at: null
};

const recordGroups = [
  {
    document_type: 'copd_admission_record',
    document_type_label: '入院记录',
    // 服务端排序:按 (record_date, record_time) 倒序
    // 1001(2026-06-05 09:30) > 1003(2026-06-03) > 1004(2026-06-02 10:15) > 1002(2026-06-01)
    tasks: [
      {
        task_id: '1001',
        display_name: '1001',
        status: 'review',
        created_at: '2026-06-07T09:00:00+08:00',
        updated_at: '2026-06-07T09:30:00+08:00',
        page_count: 2,
        document_type: 'copd_admission_record',
        document_type_label: '入院记录',
        record_date: '2026-06-05',
        record_time: '09:30'
      },
      {
        task_id: '1003',
        display_name: '1003',
        status: 'uploading',
        created_at: '2026-06-07T08:00:00+08:00',
        updated_at: '2026-06-07T08:00:00+08:00',
        page_count: 0,
        document_type: 'copd_admission_record',
        document_type_label: '入院记录',
        record_date: '2026-06-03',
        record_time: null
      },
      {
        task_id: '1004',
        display_name: '1004',
        status: 'failed',
        created_at: '2026-06-07T07:00:00+08:00',
        updated_at: '2026-06-07T07:30:00+08:00',
        page_count: 1,
        document_type: 'copd_admission_record',
        document_type_label: '入院记录',
        record_date: '2026-06-02',
        record_time: '10:15',
        error_code: 'ALGO_FAIL',
        error_message: '处理失败'
      },
      {
        task_id: '1002',
        display_name: '1002',
        status: 'done',
        created_at: '2026-06-07T10:00:00+08:00',
        updated_at: '2026-06-07T10:30:00+08:00',
        page_count: 1,
        document_type: 'copd_admission_record',
        document_type_label: '入院记录',
        record_date: '2026-06-01',
        record_time: null
      }
    ]
  },
  {
    document_type: 'discharge_summary',
    document_type_label: '出院小结',
    tasks: [
      {
        task_id: '2001',
        display_name: '2001',
        status: 'processing',
        created_at: '2026-06-07T11:00:00+08:00',
        updated_at: '2026-06-07T11:00:00+08:00',
        page_count: 1,
        document_type: 'discharge_summary',
        document_type_label: '出院小结',
        record_date: '2026-06-04',
        record_time: null
      }
    ]
  }
];

const reviewResultPayload = {
  task_id: '1001',
  status: 'review',
  review_result: {
    ocr_text: '',
    pages: [],
    field_groups: [
      {
        group_key: 'basic',
        group_label: '基本信息',
        fields: [
          { field_key: 'patient_name', label: '姓名' },
          { field_key: 'gender', label: '性别' }
        ]
      },
      {
        group_key: 'symptom',
        group_label: '症状',
        fields: [{ field_key: 'chief_complaint', label: '主诉' }]
      }
    ],
    fields: [
      {
        field_key: 'patient_name',
        label: '姓名',
        value: '张三',
        status: 'unreviewed'
      },
      {
        field_key: 'chief_complaint',
        label: '主诉',
        value: '头痛三天',
        status: 'unreviewed'
      }
    ]
  }
};

const doneReviewResultPayload = {
  task_id: '1002',
  status: 'done',
  review_result: {
    ocr_text: '',
    pages: [],
    field_groups: [
      {
        group_key: 'basic',
        group_label: '基本信息',
        fields: [{ field_key: 'patient_name', label: '姓名' }]
      }
    ],
    fields: [
      {
        field_key: 'patient_name',
        label: '姓名',
        value: '李四',
        status: 'confirmed'
      }
    ]
  }
};

function mockPatientDetail(overrides?: { records?: unknown; patient?: unknown }) {
  const recordsBody = overrides?.records ?? {
    patient: patientRecord,
    record_groups: recordGroups
  };
  const patientBody = overrides?.patient ?? patientRecord;
  return [
    http.get(`*/api/patients/${patientId}`, () =>
      HttpResponse.json({ success: true, data: patientBody })
    ),
    http.get(`*/api/patients/${patientId}/records`, () =>
      HttpResponse.json({ success: true, data: recordsBody })
    )
  ];
}

function mockReviewRoutes() {
  return [
    http.get('*/api/tasks/1001/review', () =>
      HttpResponse.json({ success: true, data: reviewResultPayload })
    ),
    http.get('*/api/tasks/1002/review', () =>
      HttpResponse.json({ success: true, data: doneReviewResultPayload })
    )
  ];
}

function renderDetail() {
  window.history.pushState({}, '', `/patients/${patientId}`);
  server.use(...mockPatientDetail(), ...mockReviewRoutes());
  return render(<PatientDetailPage />);
}

describe('PatientDetailPage', () => {
  beforeEach(() => {
    window.history.pushState({}, '', `/patients/${patientId}`);
  });

  afterEach(() => {
    vi.useRealTimers();
  });

  it('renders the workstation navigation with patients management highlighted', async () => {
    renderDetail();

    const nav = await screen.findByLabelText('工作站导航');
    const patientsLink = within(nav).getByRole('link', { name: '患者管理' });
    expect(patientsLink.getAttribute('href')).toBe('/patients');
    expect(patientsLink.getAttribute('aria-current')).toBe('page');
    expect(patientsLink.className).toContain('is-active');
  });

  it('shows patient name, id, and rename/create/delete actions in the header', async () => {
    renderDetail();

    const header = await screen.findByLabelText('患者头部');
    expect(within(header).getByText('测试用例')).toBeTruthy();
    expect(within(header).getByText(patientId)).toBeTruthy();
    expect(within(header).getByRole('button', { name: '修改姓名' })).toBeTruthy();
    expect(within(header).getByRole('button', { name: '新建该患者任务' })).toBeTruthy();
    expect(within(header).getByRole('button', { name: '删除患者' })).toBeTruthy();
  });

  it('shows record type navigation on the left with task counts', async () => {
    renderDetail();

    const nav = await screen.findByLabelText('记录类型导航');
    // 服务端顺序:入院记录在前(3 个 1 个 1 个,共 4),出院小结在后(1 个)
    expect(within(nav).getByText('入院记录')).toBeTruthy();
    expect(within(nav).getByText('出院小结')).toBeTruthy();
    // counts shown
    expect(within(nav).getByText('4')).toBeTruthy();
    expect(within(nav).getByText('1')).toBeTruthy();
  });

  it('selects the first group by default and shows timeline in server order', async () => {
    renderDetail();

    await screen.findByText('入院记录');
    const timeline = await screen.findByLabelText('任务时间轴');
    // 默认选择第一组,按服务端排序:1001(review) → 1004(failed) → 1003(uploading) → 1002(done)
    // 实际服务端 sort_key 是 (record_date, record_time) 倒序
    //   1001: 2026-06-05 09:30
    //   1004: 2026-06-02 10:15
    //   1003: 2026-06-03 (无时间)
    //   1002: 2026-06-01 (无时间)
    // 倒序应为 1001 → 1003 → 1004 → 1002
    const items = within(timeline).getAllByTestId(/^patient-record-task-/);
    expect(items.length).toBe(4);
    expect(items[0].getAttribute('data-testid')).toBe('patient-record-task-1001');
    expect(items[1].getAttribute('data-testid')).toBe('patient-record-task-1003');
    expect(items[2].getAttribute('data-testid')).toBe('patient-record-task-1004');
    expect(items[3].getAttribute('data-testid')).toBe('patient-record-task-1002');
  });

  it('does not request review result for uploading/processing/failed tasks', async () => {
    const reviewSpy = vi.fn();
    server.use(...mockPatientDetail(), ...mockReviewRoutes());
    server.use(
      http.get('*/api/tasks/1003/review', () => {
        reviewSpy();
        return HttpResponse.json({ success: true, data: reviewResultPayload });
      }),
      http.get('*/api/tasks/1004/review', () => {
        reviewSpy();
        return HttpResponse.json({ success: true, data: reviewResultPayload });
      })
    );
    render(<PatientDetailPage />);

    await screen.findByText('入院记录');
    // 触发 clicking non-review tasks 不应调用审核接口
    await userEvent.click(screen.getByTestId('patient-record-task-1003'));
    await userEvent.click(screen.getByTestId('patient-record-task-1004'));
    expect(reviewSpy).not.toHaveBeenCalled();
  });

  it('loads review result on demand when a review task is expanded', async () => {
    const reviewSpy = vi.fn();
    server.use(...mockPatientDetail());
    server.use(
      http.get('*/api/tasks/1001/review', () => {
        reviewSpy();
        return HttpResponse.json({ success: true, data: reviewResultPayload });
      })
    );
    render(<PatientDetailPage />);

    await screen.findByText('入院记录');
    expect(reviewSpy).not.toHaveBeenCalled();
    await userEvent.click(screen.getByTestId('patient-record-task-1001'));
    await waitFor(() => expect(reviewSpy).toHaveBeenCalledTimes(1));
    // 字段已渲染
    expect(await screen.findByText('基本信息')).toBeTruthy();
    expect(screen.getByText('症状')).toBeTruthy();
    expect(screen.getByText('张三')).toBeTruthy();
    expect(screen.getByText('头痛三天')).toBeTruthy();
  });

  it('loads review result on demand when a done task is expanded', async () => {
    const reviewSpy = vi.fn();
    server.use(...mockPatientDetail());
    server.use(
      http.get('*/api/tasks/1002/review', () => {
        reviewSpy();
        return HttpResponse.json({ success: true, data: doneReviewResultPayload });
      })
    );
    render(<PatientDetailPage />);

    await screen.findByText('入院记录');
    await userEvent.click(screen.getByTestId('patient-record-task-1002'));
    await waitFor(() => expect(reviewSpy).toHaveBeenCalledTimes(1));
    expect(await screen.findByText('李四')).toBeTruthy();
  });

  it('shows all schema fields in groups including empty ones', async () => {
    renderDetail();

    await screen.findByText('入院记录');
    await userEvent.click(screen.getByTestId('patient-record-task-1001'));

    const basicGroup = await screen.findByLabelText('基本信息');
    // group count "2 个字段" 因为 schema 里定义了 2 个字段(包含空的性别)
    expect(within(basicGroup).getByText('2 个字段')).toBeTruthy();
    expect(within(basicGroup).getByText('姓名')).toBeTruthy();
    // 性别虽然后端没返回字段值,但仍需展示
    expect(within(basicGroup).getByText('性别')).toBeTruthy();
  });

  it('navigates to review page when 进入审核/查看结果 is clicked', async () => {
    renderDetail();

    await screen.findByText('入院记录');
    await userEvent.click(screen.getByTestId('patient-record-task-1001'));

    const reviewLink = await screen.findByRole('link', { name: '进入审核' });
    expect(reviewLink.getAttribute('href')).toBe('/tasks/1001/review');

    // done 任务展开后跳转"查看结果"
    await userEvent.click(screen.getByTestId('patient-record-task-1002'));
    await waitFor(() => {
      const doneLink = screen.getByRole('link', { name: '查看结果' });
      expect(doneLink.getAttribute('href')).toBe('/tasks/1002/review');
    });
  });

  it('refreshes header and record groups after rename', async () => {
    const user = userEvent.setup();
    let patchBody: { name: string } | null = null;
    let recordsCallCount = 0;
    const initialRecordGroups = [
      {
        document_type: 'copd_admission_record',
        document_type_label: '入院记录',
        tasks: [
          {
            task_id: '1001',
            display_name: '1001',
            status: 'review',
            created_at: '2026-06-07T09:00:00+08:00',
            updated_at: '2026-06-07T09:30:00+08:00',
            page_count: 2,
            document_type: 'copd_admission_record',
            document_type_label: '入院记录',
            record_date: '2026-06-05',
            record_time: '09:30'
          }
        ]
      }
    ];
    server.use(
      http.get(`*/api/patients/${patientId}`, () =>
        HttpResponse.json({ success: true, data: patientRecord })
      ),
      http.get(`*/api/patients/${patientId}/records`, () => {
        recordsCallCount += 1;
        const isRefresh = recordsCallCount > 1;
        return HttpResponse.json({
          success: true,
          data: {
            patient: isRefresh
              ? { ...patientRecord, name: '新名字' }
              : patientRecord,
            record_groups: initialRecordGroups
          }
        });
      }),
      http.patch(`*/api/patients/${patientId}`, async ({ request }) => {
        patchBody = (await request.json()) as { name: string };
        return HttpResponse.json({
          success: true,
          data: {
            ...patientRecord,
            name: patchBody.name,
            updated_at: '2026-06-07T11:00:00+08:00'
          }
        });
      })
    );
    render(<PatientDetailPage />);

    await screen.findByText('测试用例');
    await user.click(screen.getByRole('button', { name: '修改姓名' }));

    const input = await screen.findByLabelText('新患者姓名');
    await user.clear(input);
    await user.type(input, '新名字');
    await user.click(screen.getByRole('button', { name: '保存' }));

    await waitFor(() => expect(patchBody).toEqual({ name: '新名字' }));
    expect(await screen.findByText('新名字')).toBeTruthy();
  });
});
