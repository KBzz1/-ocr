import { useCallback, useEffect, useRef, useState } from 'react';

import { getApiErrorMessage } from '../../api/client';
import {
  createPatient,
  getPatients,
  type PatientSummary
} from '../../api/patients';
import { createTask, type CreateTaskInput, type CreateTaskResult } from '../../api/tasks';
import { buildPatientPath } from '../../app/routes';
import { WorkstationLayout } from '../../components/layout/WorkstationLayout';
import { CaptureQrDialog } from '../../components/workstation/CaptureQrDialog';
import { CreateTaskDialog } from '../../components/workstation/CreateTaskDialog';
import type { TaskUploadSummary } from '../workstation/workstation.types';
import './patients.css';

function formatLatestRecord(value: string | null | undefined) {
  if (!value) return '暂无';
  return value;
}

function navigateToPatient(patientId: string) {
  window.history.pushState({}, '', buildPatientPath(patientId));
  window.dispatchEvent(new PopStateEvent('popstate'));
}

function toTaskUploadSummary(task: CreateTaskResult | null): TaskUploadSummary | null {
  if (!task) return null;
  return {
    ...task,
    id: task.task_id,
    displayName: task.display_name ?? task.task_id,
    uploadedPages: 0,
    createdAtText: '刚刚'
  };
}

export function PatientsPage() {
  const [query, setQuery] = useState('');
  const [submittedQuery, setSubmittedQuery] = useState('');
  const [patients, setPatients] = useState<PatientSummary[] | null>(null);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [isSearching, setIsSearching] = useState(false);
  const [isCreateOpen, setIsCreateOpen] = useState(false);
  const [newName, setNewName] = useState('');
  const [isCreating, setIsCreating] = useState(false);
  const [createError, setCreateError] = useState<string | null>(null);
  const [taskDialogPatient, setTaskDialogPatient] = useState<{ patient_id: string; name: string } | null>(null);
  const [isTaskCreating, setIsTaskCreating] = useState(false);
  const [createdQrTask, setCreatedQrTask] = useState<CreateTaskResult | null>(null);
  // 跟踪最新查询序号,避免慢响应覆盖快响应
  const searchRequestId = useRef(0);

  const loadPatients = useCallback(async (mode: 'initial' | 'search', searchTerm: string) => {
    const requestId = searchRequestId.current + 1;
    searchRequestId.current = requestId;
    if (mode === 'initial') {
      setIsSearching(true);
    } else {
      setIsSearching(true);
    }
    setLoadError(null);
    try {
      const results = await getPatients(searchTerm || undefined);
      if (requestId !== searchRequestId.current) return;
      setPatients(results);
    } catch (error) {
      if (requestId !== searchRequestId.current) return;
      setLoadError(getApiErrorMessage(error, '患者列表加载失败,请重试'));
      setPatients([]);
    } finally {
      if (requestId === searchRequestId.current) {
        setIsSearching(false);
      }
    }
  }, []);

  useEffect(() => {
    void loadPatients('initial', '');
  }, [loadPatients]);

  async function handleSearch(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (isSearching) return;
    const trimmed = query.trim();
    setSubmittedQuery(trimmed);
    await loadPatients('search', trimmed);
  }

  function handleOpenCreate() {
    setCreateError(null);
    setNewName('');
    setIsCreateOpen(true);
  }

  function handleCancelCreate() {
    if (isCreating) return;
    setIsCreateOpen(false);
    setCreateError(null);
    setNewName('');
  }

  async function handleSubmitCreate(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const trimmed = newName.trim();
    if (!trimmed) {
      setCreateError('请输入患者姓名');
      return;
    }
    setIsCreating(true);
    setCreateError(null);
    try {
      const created = await createPatient({ name: trimmed });
      setIsCreateOpen(false);
      setNewName('');
      setPatients((current) => [
        {
          ...created,
          task_count: 0,
          latest_record_at: null
        },
        ...(current ?? [])
      ]);
      navigateToPatient(created.patient_id);
    } catch (error) {
      setCreateError(getApiErrorMessage(error, '新建患者失败,请重试'));
    } finally {
      setIsCreating(false);
    }
  }

  function handleOpenTaskDialog(patient: PatientSummary) {
    setTaskDialogPatient({ patient_id: patient.patient_id, name: patient.name });
  }

  function handleCloseTaskDialog() {
    if (isTaskCreating) return;
    setTaskDialogPatient(null);
  }

  async function handleSubmitTask(input: CreateTaskInput) {
    if (isTaskCreating) return;
    setIsTaskCreating(true);
    try {
      const result = await createTask(input);
      setTaskDialogPatient(null);
      setCreatedQrTask(result);
      await loadPatients('search', submittedQuery);
    } finally {
      setIsTaskCreating(false);
    }
  }

  const statusText = loadError
    ? loadError
    : isSearching
      ? '正在加载患者'
      : patients
        ? `共 ${patients.length} 位患者${submittedQuery ? `（关键词：${submittedQuery}）` : ''}`
        : '正在加载患者';

  return (
    <WorkstationLayout activeRouteId="patients" headerKicker="" headerTitle="">
      <main className="patients-page" aria-label="患者管理页">
        <header className="patients-page__header">
          <div className="patients-page__title">
            <h1>患者管理</h1>
          </div>
          <form className="patients-search-bar" onSubmit={handleSearch} role="search" aria-label="搜索患者">
            <input
              type="search"
              className="patients-search-input"
              value={query}
              onChange={(event) => setQuery(event.currentTarget.value)}
              placeholder="按患者姓名或患者编号搜索"
              aria-label="按患者姓名或患者编号搜索"
              autoComplete="off"
            />
            <button
              type="submit"
              className="patients-search-button"
              disabled={isSearching}
              aria-label="搜索"
            >
              {isSearching ? '搜索中' : '搜索'}
            </button>
            <button
              type="button"
              className="patients-new-button"
              onClick={handleOpenCreate}
            >
              新建患者
            </button>
          </form>
        </header>

        <div className="patients-page__content">
          <p className={loadError ? 'patients-page__status patients-page__error' : 'patients-page__status'}>
            {statusText}
          </p>

          {isCreateOpen ? (
            <form className="patients-new-form" onSubmit={handleSubmitCreate} aria-label="新建患者">
              <input
                type="text"
                value={newName}
                onChange={(event) => setNewName(event.currentTarget.value)}
                placeholder="输入患者姓名"
                aria-label="患者姓名"
                autoComplete="off"
                disabled={isCreating}
              />
              <button
                type="submit"
                className="patients-search-button"
                disabled={isCreating}
              >
                {isCreating ? '正在创建' : '创建'}
              </button>
              <button
                type="button"
                className="patients-new-button"
                onClick={handleCancelCreate}
                disabled={isCreating}
              >
                取消
              </button>
              {createError ? (
                <span className="patients-page__error" role="alert">
                  {createError}
                </span>
              ) : null}
            </form>
          ) : null}

          <div className="patients-table-wrap">
            <table className="patients-table" aria-label="患者列表">
              <thead>
                <tr>
                  <th scope="col">患者姓名</th>
                  <th scope="col">患者编号</th>
                  <th scope="col">最近记录时间</th>
                  <th scope="col">操作</th>
                </tr>
              </thead>
              <tbody>
                {patients === null ? null : patients.length === 0 ? (
                  <tr>
                    <td colSpan={4} className="patients-table__empty">
                      <strong>未找到匹配的患者</strong>
                      <div>尝试更换关键词或新建患者</div>
                    </td>
                  </tr>
                ) : (
                  patients.map((patient) => (
                    <tr key={patient.patient_id}>
                      <td>
                        <button
                          type="button"
                          className="patients-table__name-button"
                          onClick={() => navigateToPatient(patient.patient_id)}
                        >
                          {patient.name}
                        </button>
                        <div className="patients-table__subtext">{patient.task_count} 个任务</div>
                      </td>
                      <td>
                        <span className="patients-table__id">{patient.patient_id}</span>
                      </td>
                      <td>{formatLatestRecord(patient.latest_record_at)}</td>
                      <td>
                        <div className="patients-table__actions">
                          <button
                            type="button"
                            className="patients-table__detail-button"
                            onClick={() => navigateToPatient(patient.patient_id)}
                          >
                            查看详情
                          </button>
                          <button
                            type="button"
                            className="patients-table__task-button"
                            onClick={() => handleOpenTaskDialog(patient)}
                          >
                            新建任务
                          </button>
                        </div>
                      </td>
                    </tr>
                  ))
                )}
              </tbody>
            </table>
          </div>
        </div>
      </main>
      <CreateTaskDialog
        isOpen={Boolean(taskDialogPatient)}
        isSubmitting={isTaskCreating}
        initialPatient={taskDialogPatient}
        onClose={handleCloseTaskDialog}
        onSubmit={handleSubmitTask}
      />
      <CaptureQrDialog
        isOpen={Boolean(createdQrTask)}
        task={toTaskUploadSummary(createdQrTask)}
        onClose={() => setCreatedQrTask(null)}
      />
    </WorkstationLayout>
  );
}
