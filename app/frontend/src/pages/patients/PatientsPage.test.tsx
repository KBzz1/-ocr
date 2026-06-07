import { render, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { http, HttpResponse } from 'msw';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import { server } from '../../../tests/setupTests';
import { PatientsPage } from './PatientsPage';

function mockPatientList(
  patients: Array<{
    patient_id: string;
    name: string;
    task_count?: number;
    latest_record_at?: string | null;
  }>
) {
  return http.get('*/api/patients', ({ request }) => {
    const url = new URL(request.url);
    const query = url.searchParams.get('query') ?? '';
    const filtered = query
      ? patients.filter(
          (patient) =>
            patient.name.includes(query) || patient.patient_id.includes(query)
        )
      : patients;
    return HttpResponse.json({
      success: true,
      data: {
        patients: filtered.map((patient) => ({
          patient_id: patient.patient_id,
          name: patient.name,
          created_at: '2026-06-07T10:00:00+08:00',
          updated_at: '2026-06-07T10:00:00+08:00',
          deleted_at: null,
          task_count: patient.task_count ?? 0,
          latest_record_at: patient.latest_record_at ?? null
        }))
      }
    });
  });
}

const patientFixtures = [
  {
    patient_id: 'P-A1B2C3D4',
    name: '测试用例',
    task_count: 2,
    latest_record_at: '2026-06-05'
  },
  {
    patient_id: 'P-E5F6A7B8',
    name: '其他患者',
    task_count: 0,
    latest_record_at: null
  }
];

function renderPatients() {
  window.history.pushState({}, '', '/patients');
  server.use(mockPatientList(patientFixtures));
  return render(<PatientsPage />);
}

describe('PatientsPage', () => {
  beforeEach(() => {
    window.history.pushState({}, '', '/patients');
  });

  afterEach(() => {
    vi.useRealTimers();
  });

  it('renders main navigation with patients management highlighted', async () => {
    renderPatients();

    const nav = await screen.findByLabelText('工作站导航');
    const patientsLink = within(nav).getByRole('link', { name: '患者管理' });
    expect(patientsLink.getAttribute('href')).toBe('/patients');
    expect(patientsLink.getAttribute('aria-current')).toBe('page');
    expect(patientsLink.className).toContain('is-active');
  });

  it('renders patient list with name, id, task count, and latest record', async () => {
    renderPatients();

    const table = await screen.findByRole('table', { name: '患者列表' });
    const row = within(table).getByText('P-A1B2C3D4').closest('tr') as HTMLElement;
    expect(row.textContent).toContain('测试用例');
    expect(row.textContent).toContain('2');
    expect(row.textContent).toContain('2026-06-05');

    expect(within(table).getByText('P-E5F6A7B8')).toBeTruthy();
  });

  it('searches by name or patient id and updates the list', async () => {
    const user = userEvent.setup();
    server.use(mockPatientList(patientFixtures));
    render(<PatientsPage />);

    const searchInput = await screen.findByLabelText('按患者姓名或患者编号搜索');
    await user.type(searchInput, 'P-A1B2C3D4');
    await user.click(screen.getByRole('button', { name: '搜索' }));

    const table = await screen.findByRole('table', { name: '患者列表' });
    await waitFor(() => {
      expect(within(table).getByText('P-A1B2C3D4')).toBeTruthy();
    });
    expect(within(table).queryByText('P-E5F6A7B8')).toBeNull();
  });

  it('disables search button during in-flight request and avoids concurrent calls', async () => {
    const user = userEvent.setup();
    let searchCallCount = 0;
    let release: () => void = () => undefined;
    server.use(
      http.get('*/api/patients', async ({ request }) => {
        searchCallCount += 1;
        const url = new URL(request.url);
        const query = url.searchParams.get('query') ?? '';
        // 第一次请求保持挂起,模拟慢响应
        if (searchCallCount === 1) {
          await new Promise<void>((resolve) => {
            release = resolve;
          });
        }
        const filtered = query
          ? patientFixtures.filter(
              (patient) =>
                patient.name.includes(query) || patient.patient_id.includes(query)
            )
          : patientFixtures;
        return HttpResponse.json({
          success: true,
          data: {
            patients: filtered.map((patient) => ({
              patient_id: patient.patient_id,
              name: patient.name,
              created_at: '2026-06-07T10:00:00+08:00',
              updated_at: '2026-06-07T10:00:00+08:00',
              deleted_at: null,
              task_count: patient.task_count ?? 0,
              latest_record_at: patient.latest_record_at ?? null
            }))
          }
        });
      })
    );
    render(<PatientsPage />);

    const searchInput = await screen.findByLabelText('按患者姓名或患者编号搜索');
    await user.type(searchInput, '测试');

    const searchButton = screen.getByRole('button', { name: '搜索' });
    await user.click(searchButton);

    await waitFor(() => expect(searchButton.textContent).toBe('搜索中'));
    expect((searchButton as HTMLButtonElement).disabled).toBe(true);

    // 在请求挂起期间再次点击,按钮禁用不会触发新请求
    await user.click(searchButton).catch(() => undefined);

    expect(searchCallCount).toBe(1);

    release();
    await waitFor(() => expect(searchButton.textContent).toBe('搜索'));
  });

  it('creates a new patient and navigates to the detail page', async () => {
    const user = userEvent.setup();
    let createBody: { name: string } | null = null;
    server.use(
      mockPatientList(patientFixtures),
      http.post('*/api/patients', async ({ request }) => {
        createBody = (await request.json()) as { name: string };
        return HttpResponse.json({
          success: true,
          data: {
            patient_id: 'P-NEWPAT99',
            name: createBody.name,
            created_at: '2026-06-07T10:00:00+08:00',
            updated_at: '2026-06-07T10:00:00+08:00',
            deleted_at: null
          }
        });
      })
    );
    render(<PatientsPage />);

    await screen.findByRole('table', { name: '患者列表' });
    await user.click(screen.getByRole('button', { name: '新建患者' }));

    const newNameInput = await screen.findByLabelText('患者姓名');
    await user.type(newNameInput, '新患者');

    await user.click(screen.getByRole('button', { name: '创建' }));

    await waitFor(() => expect(createBody).toEqual({ name: '新患者' }));
    await waitFor(() => expect(window.location.pathname).toBe('/patients/P-NEWPAT99'));
  });

  it('navigates to patient detail when a row is clicked', async () => {
    const user = userEvent.setup();
    renderPatients();

    const table = await screen.findByRole('table', { name: '患者列表' });
    const row = within(table).getByText('P-A1B2C3D4').closest('tr') as HTMLElement;
    const nameButton = within(row).getByRole('button', { name: '测试用例' });
    await user.click(nameButton);

    expect(window.location.pathname).toBe('/patients/P-A1B2C3D4');
  });
});
