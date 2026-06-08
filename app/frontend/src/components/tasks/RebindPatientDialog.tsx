import { useEffect, useState } from 'react';

import { getApiErrorMessage } from '../../api/client';
import { createPatient, getPatients, type PatientSummary } from '../../api/patients';
import type { TaskSummary } from '../../api/tasks';
import { IconButton } from '../common/IconButton';

type RebindPatientDialogProps = {
  isOpen: boolean;
  task: TaskSummary | null;
  isSubmitting: boolean;
  onClose: () => void;
  onSubmit: (patientId: string) => Promise<void>;
};

export function RebindPatientDialog({
  isOpen,
  task,
  isSubmitting,
  onClose,
  onSubmit
}: RebindPatientDialogProps) {
  const [name, setName] = useState('');
  const [searchResults, setSearchResults] = useState<PatientSummary[] | null>(null);
  const [isSearching, setIsSearching] = useState(false);
  const [isCreating, setIsCreating] = useState(false);
  const [selectedPatient, setSelectedPatient] = useState<PatientSummary | null>(null);
  const [createdPatient, setCreatedPatient] = useState<PatientSummary | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [submitError, setSubmitError] = useState<string | null>(null);

  useEffect(() => {
    if (isOpen) {
      setName('');
      setSearchResults(null);
      setIsSearching(false);
      setIsCreating(false);
      setSelectedPatient(null);
      setCreatedPatient(null);
      setError(null);
      setSubmitError(null);
    }
  }, [isOpen, task?.task_id]);

  if (!isOpen || !task) return null;

  async function handleSearch() {
    const trimmed = name.trim();
    setError(null);
    setSelectedPatient(null);
    if (!trimmed) {
      setError('请输入患者姓名后再搜索');
      setSearchResults(null);
      return;
    }
    setIsSearching(true);
    try {
      const patients = await getPatients(trimmed);
      // 排除当前任务的患者(改绑到相同患者无意义)
      const filtered = patients.filter((p) => p.patient_id !== task?.patient?.patient_id);
      setSearchResults(filtered);
    } catch (searchError: unknown) {
      setError(getApiErrorMessage(searchError, '患者搜索失败,请重试'));
      setSearchResults(null);
    } finally {
      setIsSearching(false);
    }
  }

  async function handleCreate() {
    const trimmed = name.trim();
    setError(null);
    if (!trimmed) {
      setError('请输入患者姓名后再新建');
      return;
    }
    setIsCreating(true);
    try {
      const created = await createPatient({ name: trimmed });
      const summary: PatientSummary = {
        ...created,
        task_count: 0,
        latest_record_at: null
      };
      setCreatedPatient(summary);
      setSelectedPatient(summary);
      setSearchResults([summary]);
    } catch (createError: unknown) {
      setError(getApiErrorMessage(createError, '新建患者失败,请重试'));
    } finally {
      setIsCreating(false);
    }
  }

  function handleSelect(patient: PatientSummary) {
    setSelectedPatient(patient);
    setSubmitError(null);
  }

  async function handleConfirm() {
    if (!selectedPatient) {
      setSubmitError('请先选择或新建患者');
      return;
    }
    setSubmitError(null);
    try {
      await onSubmit(selectedPatient.patient_id);
    } catch (submitErrorCatch: unknown) {
      setSubmitError(getApiErrorMessage(submitErrorCatch, '改绑失败,请重试'));
    }
  }

  const currentPatient = task.patient;
  const isProcessing = task.status === 'processing';

  return (
    <div className="qr-dialog-backdrop" role="presentation" onMouseDown={onClose}>
      <section
        className="qr-dialog rebind-patient-dialog"
        role="dialog"
        aria-modal="true"
        aria-label="改绑患者"
        aria-labelledby="rebind-patient-dialog-title"
        onMouseDown={(event) => event.stopPropagation()}
      >
        <header className="qr-dialog__header">
          <div>
            <h2 id="rebind-patient-dialog-title">改绑患者</h2>
            <p className="rebind-patient-dialog__subtitle">
              任务 <strong>{task.display_name ?? task.task_id}</strong>
              {currentPatient ? (
                <>
                  {' '}当前患者:<strong>{currentPatient.name}</strong>({currentPatient.patient_id})
                </>
              ) : null}
            </p>
          </div>
          <IconButton label="关闭弹窗" onClick={onClose} variant="soft">
            x
          </IconButton>
        </header>

        <div className="rebind-patient-dialog__body">
          {isProcessing ? (
            <div className="rebind-patient-dialog__notice" role="status">
              任务正在处理,处理中不允许改绑患者;请等待处理完成或先取消处理。
            </div>
          ) : null}

          <label className="rebind-patient-field">
            <span>患者姓名</span>
            <input
              type="text"
              value={name}
              autoComplete="off"
              disabled={isProcessing}
              onChange={(event) => {
                setName(event.currentTarget.value);
                setSelectedPatient(null);
                setSearchResults(null);
                setCreatedPatient(null);
              }}
              placeholder="输入患者姓名"
              aria-label="患者姓名"
            />
          </label>

          <div className="rebind-patient-actions">
            <button
              type="button"
              className="secondary-action"
              disabled={isProcessing || isSearching || !name.trim()}
              onClick={() => void handleSearch()}
            >
              {isSearching ? '搜索中' : '搜索'}
            </button>
            <button
              type="button"
              className="secondary-action"
              disabled={isProcessing || isCreating || !name.trim()}
              onClick={() => void handleCreate()}
            >
              {isCreating ? '正在新建' : '仍然新建'}
            </button>
          </div>

          {error ? (
            <p className="inline-error" role="alert">{error}</p>
          ) : null}

          {searchResults !== null ? (
            searchResults.length === 0 ? (
              <p className="rebind-patient-empty">未找到匹配的患者,可点击"仍然新建"创建独立档案。</p>
            ) : (
              <ul className="rebind-patient-list" aria-label="患者搜索结果">
                {searchResults.map((patient) => {
                  const isSelected = selectedPatient?.patient_id === patient.patient_id;
                  return (
                    <li key={patient.patient_id} className="rebind-patient-row">
                      <div className="rebind-patient-meta">
                        <strong>{patient.patient_id}</strong>
                        <span>姓名:{patient.name}</span>
                        <span>共 {patient.task_count} 个任务</span>
                        {patient.latest_record_at ? (
                          <span>最近记录:{patient.latest_record_at}</span>
                        ) : null}
                      </div>
                      <button
                        type="button"
                        className={isSelected ? 'primary-action' : 'secondary-action'}
                        onClick={() => handleSelect(patient)}
                      >
                        {isSelected ? '已选择' : `选择 ${patient.patient_id}`}
                      </button>
                    </li>
                  );
                })}
              </ul>
            )
          ) : null}

          {createdPatient ? (
            <p className="rebind-patient-selected" role="status">
              已新建患者:{createdPatient.patient_id}
            </p>
          ) : null}

          {selectedPatient ? (
            <p className="rebind-patient-selected" role="status">
              已选择患者:{selectedPatient.patient_id}({selectedPatient.name})
            </p>
          ) : null}

          {submitError ? (
            <p className="inline-error" role="alert">{submitError}</p>
          ) : null}
        </div>

        <footer className="qr-dialog__footer">
          <button type="button" className="ghost-action" onClick={onClose} disabled={isSubmitting}>
            取消
          </button>
          <button
            type="button"
            className="primary-action"
            disabled={isProcessing || isSubmitting || !selectedPatient}
            onClick={() => void handleConfirm()}
          >
            {isSubmitting ? '改绑中' : '确认改绑'}
          </button>
        </footer>
      </section>
    </div>
  );
}
