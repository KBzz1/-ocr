import { useCallback, useEffect, useMemo, useRef, useState } from 'react';

import { ApiError } from '../../api/client';
import {
  deletePatient,
  getPatientRecords,
  updatePatient,
  type PatientDetailResponse,
  type PatientRecord,
  type PatientRecordGroup
} from '../../api/patients';
import { getReviewResult, type ReviewField, type ReviewResult } from '../../api/review';
import { createTask, type CreateTaskInput, type CreateTaskResult, type TaskSummary } from '../../api/tasks';
import { getTaskStatusLabel, taskStatusMeta } from '../../styles/status';
import { buildPatientPath, buildReviewPath, PATIENTS_PATH_PREFIX } from '../../app/routes';
import { WorkstationLayout } from '../../components/layout/WorkstationLayout';
import { CreateTaskDialog } from '../../components/workstation/CreateTaskDialog';
import { FieldList } from '../../components/review/FieldList';
import './patients.css';

type ReviewsByTaskId = Record<string, { fields: ReviewField[]; field_groups?: ReviewResult['field_groups'] } | undefined>;

type CreateDialogState =
  | { isOpen: false; initialPatient: null; pendingTask: null }
  | { isOpen: true; initialPatient: { patient_id: string; name: string } | null; pendingTask: CreateTaskResult | null };

function getErrorMessage(error: unknown, fallback: string) {
  return error instanceof ApiError ? error.message : fallback;
}

function getPatientIdFromPath() {
  const match = window.location.pathname.match(/^\/patients\/([^/]+)\/?$/);
  return match ? decodeURIComponent(match[1] ?? '') : '';
}

function formatRecordDateLabel(recordDate?: string | null, recordTime?: string | null) {
  if (!recordDate) return '记录时间未知';
  return recordTime ? `${recordDate} ${recordTime}` : recordDate;
}

function isReviewableStatus(status: TaskSummary['status']) {
  return status === 'review' || status === 'done';
}

export function PatientDetailPage() {
  const [patientId] = useState(() => getPatientIdFromPath());
  const [patient, setPatient] = useState<PatientRecord | null>(null);
  const [recordGroups, setRecordGroups] = useState<PatientRecordGroup[]>([]);
  const [selectedGroupKey, setSelectedGroupKey] = useState<string | null>(null);
  const [expandedTaskId, setExpandedTaskId] = useState<string | null>(null);
  const [reviewsByTaskId, setReviewsByTaskId] = useState<ReviewsByTaskId>({});
  const [reviewLoadError, setReviewLoadError] = useState<{ taskId: string; message: string } | null>(null);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [isRenaming, setIsRenaming] = useState(false);
  const [renameDraft, setRenameDraft] = useState('');
  const [isRenamingSubmitting, setIsRenamingSubmitting] = useState(false);
  const [renameError, setRenameError] = useState<string | null>(null);
  const [isDeleting, setIsDeleting] = useState(false);
  const [deleteError, setDeleteError] = useState<string | null>(null);
  const [createDialog, setCreateDialog] = useState<CreateDialogState>({
    isOpen: false,
    initialPatient: null,
    pendingTask: null
  });
  const loadRequestId = useRef(0);

  const loadDetail = useCallback(async (mode: 'initial' | 'refresh') => {
    if (!patientId) {
      setLoadError('患者编号缺失');
      setIsLoading(false);
      return;
    }
    const requestId = loadRequestId.current + 1;
    loadRequestId.current = requestId;
    if (mode === 'initial') {
      setIsLoading(true);
    }
    setLoadError(null);
    try {
      // 详情聚合:patients/{id}/records 同时返回患者和按类型分组的时间轴
      const detail: PatientDetailResponse = await getPatientRecords(patientId);
      if (requestId !== loadRequestId.current) return;
      setPatient(detail.patient);
      setRecordGroups(detail.record_groups ?? []);
    } catch (error) {
      if (requestId !== loadRequestId.current) return;
      setLoadError(getErrorMessage(error, '患者详情加载失败，请重试'));
    } finally {
      if (requestId === loadRequestId.current) {
        setIsLoading(false);
      }
    }
  }, [patientId]);

  useEffect(() => {
    void loadDetail('initial');
    // 仅首次挂载 + patientId 切换时加载
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [patientId]);

  // 首次加载完成后,若未选中任何记录类型,默认选中第一组
  useEffect(() => {
    if (!selectedGroupKey && recordGroups.length > 0) {
      setSelectedGroupKey(recordGroups[0]?.document_type ?? null);
    }
  }, [recordGroups, selectedGroupKey]);

  const selectedGroup = useMemo(() => {
    if (!selectedGroupKey) return null;
    return recordGroups.find((group) => group.document_type === selectedGroupKey) ?? recordGroups[0] ?? null;
  }, [recordGroups, selectedGroupKey]);

  function handleSelectGroup(documentType: string) {
    setSelectedGroupKey(documentType);
    setExpandedTaskId(null);
  }

  const toggleRecord = useCallback(async (task: TaskSummary) => {
    if (!isReviewableStatus(task.status)) {
      // 非可审核状态:切换展开只用于切换面板,但不加载字段
      setExpandedTaskId((current) => (current === task.task_id ? null : task.task_id));
      return;
    }
    setExpandedTaskId((current) => (current === task.task_id ? null : task.task_id));
    if (reviewsByTaskId[task.task_id]) return;
    try {
      const review = await getReviewResult(task.task_id);
      setReviewsByTaskId((current) => ({
        ...current,
        [task.task_id]: { fields: review.fields, field_groups: review.field_groups }
      }));
      setReviewLoadError(null);
    } catch (error) {
      setReviewLoadError({
        taskId: task.task_id,
        message: getErrorMessage(error, '字段加载失败，请重试')
      });
    }
  }, [reviewsByTaskId]);

  function handleStartRename() {
    if (!patient) return;
    setRenameDraft(patient.name);
    setRenameError(null);
    setIsRenaming(true);
  }

  function handleCancelRename() {
    setIsRenaming(false);
    setRenameError(null);
  }

  async function handleCommitRename() {
    if (!patient) return;
    const trimmed = renameDraft.trim();
    setIsRenaming(false);
    if (!trimmed || trimmed === patient.name) {
      return;
    }
    setIsRenamingSubmitting(true);
    setRenameError(null);
    try {
      const updated = await updatePatient(patientId, { name: trimmed });
      setPatient((current) => (current ? { ...current, ...updated } : current));
      // 改名后刷新详情聚合,确保任务里的 patient_snapshot 也及时反映
      await loadDetail('refresh');
    } catch (error) {
      setRenameError(getErrorMessage(error, '修改姓名失败，请重试'));
    } finally {
      setIsRenamingSubmitting(false);
    }
  }

  async function handleDeletePatient() {
    if (!patient || isDeleting) return;
    if (!window.confirm(`确认逻辑删除患者「${patient.name}」？\n将仅删除患者档案,关联任务保留。`)) {
      return;
    }
    setIsDeleting(true);
    setDeleteError(null);
    try {
      await deletePatient(patientId, false);
      window.history.pushState({}, '', PATIENTS_PATH_PREFIX);
      window.dispatchEvent(new PopStateEvent('popstate'));
    } catch (error) {
      setDeleteError(getErrorMessage(error, '删除患者失败，请重试'));
    } finally {
      setIsDeleting(false);
    }
  }

  function handleOpenCreateDialog() {
    if (!patient) return;
    setCreateDialog({
      isOpen: true,
      initialPatient: { patient_id: patient.patient_id, name: patient.name },
      pendingTask: null
    });
  }

  function handleCloseCreateDialog() {
    if (createDialog.pendingTask) return;
    setCreateDialog({ isOpen: false, initialPatient: null, pendingTask: null });
  }

  async function handleSubmitCreate(input: CreateTaskInput) {
    try {
      const result = await createTask(input);
      setCreateDialog({ isOpen: true, initialPatient: null, pendingTask: result });
      await loadDetail('refresh');
    } catch (error) {
      throw error;
    }
  }

  function handleCloseCreateResult() {
    setCreateDialog({ isOpen: false, initialPatient: null, pendingTask: null });
  }

  if (!patientId) {
    return (
      <WorkstationLayout activeRouteId="patients" headerKicker="" headerTitle="">
        <main className="patients-page" aria-label="患者详情页">
          <p role="alert" className="patients-page__error">患者编号缺失，无法加载详情</p>
        </main>
      </WorkstationLayout>
    );
  }

  if (isLoading) {
    return (
      <WorkstationLayout activeRouteId="patients" headerKicker="" headerTitle="">
        <main className="patients-page" aria-label="患者详情页">
          <p className="patients-page__status">正在加载患者详情</p>
        </main>
      </WorkstationLayout>
    );
  }

  if (loadError) {
    return (
      <WorkstationLayout activeRouteId="patients" headerKicker="" headerTitle="">
        <main className="patients-page" aria-label="患者详情页">
          <p role="alert" className="patients-page__error">{loadError}</p>
        </main>
      </WorkstationLayout>
    );
  }

  if (!patient) {
    return (
      <WorkstationLayout activeRouteId="patients" headerKicker="" headerTitle="">
        <main className="patients-page" aria-label="患者详情页">
          <p className="patients-page__status">未找到该患者</p>
        </main>
      </WorkstationLayout>
    );
  }

  return (
    <WorkstationLayout activeRouteId="patients" headerKicker="" headerTitle="">
      <main className="patient-detail-page" aria-label="患者详情页">
        <header className="patient-detail-page__header" aria-label="患者头部">
          <div className="patient-detail-page__identity">
            <h1 className="patient-detail-page__name">{patient.name}</h1>
            <span className="patient-detail-page__id">{patient.patient_id}</span>
          </div>
          <div className="patient-detail-page__actions">
            {isRenaming ? (
              <form
                className="patient-detail-page__rename-form"
                onSubmit={(event) => {
                  event.preventDefault();
                  void handleCommitRename();
                }}
              >
                <label className="patient-detail-page__rename-label" htmlFor="patient-detail-rename-input">新患者姓名</label>
                <input
                  id="patient-detail-rename-input"
                  className="patient-detail-page__rename-input"
                  type="text"
                  value={renameDraft}
                  autoFocus
                  disabled={isRenamingSubmitting}
                  onChange={(event) => setRenameDraft(event.currentTarget.value)}
                  onKeyDown={(event) => {
                    if (event.key === 'Escape') handleCancelRename();
                  }}
                />
                <button
                  type="submit"
                  className="patient-detail-page__rename-submit"
                  disabled={isRenamingSubmitting || !renameDraft.trim()}
                >
                  保存
                </button>
                <button
                  type="button"
                  className="patient-detail-page__rename-cancel"
                  onClick={handleCancelRename}
                  disabled={isRenamingSubmitting}
                >
                  取消
                </button>
              </form>
            ) : (
              <button
                type="button"
                className="patient-detail-page__action"
                onClick={handleStartRename}
                disabled={!patient}
              >
                修改姓名
              </button>
            )}
            <button
              type="button"
              className="patient-detail-page__action"
              onClick={handleOpenCreateDialog}
            >
              新建该患者任务
            </button>
            <button
              type="button"
              className="patient-detail-page__action patient-detail-page__action--danger"
              onClick={() => void handleDeletePatient()}
              disabled={isDeleting}
            >
              {isDeleting ? '删除中' : '删除患者'}
            </button>
          </div>
        </header>
        {renameError ? (
          <p role="alert" className="patient-detail-page__alert">{renameError}</p>
        ) : null}
        {deleteError ? (
          <p role="alert" className="patient-detail-page__alert">{deleteError}</p>
        ) : null}

        <div className="patient-detail-page__content">
          <nav className="patient-detail-page__types" aria-label="记录类型导航">
            {recordGroups.length === 0 ? (
              <p className="patient-detail-page__empty">暂无任何记录</p>
            ) : (
              <ul className="patient-detail-page__type-list">
                {recordGroups.map((group) => {
                  const isActive = group.document_type === selectedGroup?.document_type;
                  return (
                    <li key={group.document_type}>
                      <button
                        type="button"
                        className={`patient-detail-page__type-button${isActive ? ' is-active' : ''}`}
                        aria-current={isActive ? 'true' : undefined}
                        onClick={() => handleSelectGroup(group.document_type)}
                      >
                        <span className="patient-detail-page__type-label">
                          {group.document_type_label || group.document_type}
                        </span>
                        <span className="patient-detail-page__type-count">{group.tasks.length}</span>
                      </button>
                    </li>
                  );
                })}
              </ul>
            )}
          </nav>

          <section className="patient-detail-page__timeline" aria-label="任务时间轴">
            {!selectedGroup ? (
              <p className="patient-detail-page__empty">未选中任何记录类型</p>
            ) : (
              <ol className="patient-detail-page__record-list">
                {selectedGroup.tasks.map((task) => {
                  const isExpanded = expandedTaskId === task.task_id;
                  const reviewData = reviewsByTaskId[task.task_id];
                  const reviewable = isReviewableStatus(task.status);
                  const statusMeta = taskStatusMeta[task.status];
                  return (
                    <li
                      key={task.task_id}
                      className="patient-detail-page__record"
                    >
                      <button
                        type="button"
                        className="patient-detail-page__record-summary"
                        onClick={() => void toggleRecord(task)}
                        aria-expanded={isExpanded}
                        data-testid={`patient-record-task-${task.task_id}`}
                      >
                        <span className="patient-detail-page__record-date">
                          {formatRecordDateLabel(task.record_date, task.record_time)}
                        </span>
                        <span className="patient-detail-page__record-id">任务 {task.display_name ?? task.task_id}</span>
                        <span className={`patient-detail-page__record-status patient-detail-page__record-status--${statusMeta.tone}`}>
                          {getTaskStatusLabel(task.status)}
                        </span>
                      </button>
                      {isExpanded ? (
                        <div className="patient-detail-page__record-detail">
                          {reviewable ? (
                            reviewData ? (
                              <FieldList
                                fields={reviewData.fields}
                                fieldGroups={reviewData.field_groups}
                                selectedFieldKey={null}
                                onChange={() => undefined}
                                onFocusField={() => undefined}
                                onToggleReviewed={() => undefined}
                                readOnly
                              />
                            ) : reviewLoadError && reviewLoadError.taskId === task.task_id ? (
                              <p role="alert" className="patient-detail-page__alert">{reviewLoadError.message}</p>
                            ) : (
                              <p className="patient-detail-page__empty">字段加载中</p>
                            )
                          ) : (
                            <p className="patient-detail-page__empty">
                              当前状态 {getTaskStatusLabel(task.status)} 暂无可展示字段
                            </p>
                          )}
                          <div className="patient-detail-page__record-actions">
                            {reviewable ? (
                              <a
                                className="patient-detail-page__record-link"
                                href={buildReviewPath(task.task_id)}
                              >
                                {task.status === 'done' ? '查看结果' : '进入审核'}
                              </a>
                            ) : null}
                          </div>
                        </div>
                      ) : null}
                    </li>
                  );
                })}
              </ol>
            )}
          </section>
        </div>
      </main>
      <CreateTaskDialog
        isOpen={createDialog.isOpen}
        isSubmitting={Boolean(createDialog.pendingTask)}
        initialPatient={createDialog.initialPatient}
        onClose={handleCloseCreateDialog}
        onSubmit={handleSubmitCreate}
      />
    </WorkstationLayout>
  );
}
