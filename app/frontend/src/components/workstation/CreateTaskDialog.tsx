import { useEffect, useMemo, useState } from 'react';

import { getApiErrorMessage } from '../../api/client';
import { createPatient, getPatients, type PatientSummary } from '../../api/patients';
import type { CreateTaskInput } from '../../api/tasks';
import { IconButton } from '../common/IconButton';

type CreateTaskDialogProps = {
  isOpen: boolean;
  isSubmitting: boolean;
  onClose: () => void;
  onSubmit: (input: CreateTaskInput) => Promise<void>;
  initialPatient?: { patient_id: string; name: string } | null;
};

type DocumentTypeOption = {
  value: string;
  label: string;
};

const DOCUMENT_TYPE_OPTIONS: DocumentTypeOption[] = [
  { value: 'copd_admission_record', label: '入院记录' }
];

function todayDateString() {
  const now = new Date();
  const year = now.getFullYear().toString().padStart(4, '0');
  const month = (now.getMonth() + 1).toString().padStart(2, '0');
  const day = now.getDate().toString().padStart(2, '0');
  return `${year}-${month}-${day}`;
}

export function CreateTaskDialog({
  isOpen,
  isSubmitting,
  onClose,
  onSubmit,
  initialPatient = null
}: CreateTaskDialogProps) {
  const [patientName, setPatientName] = useState('');
  const [searchResults, setSearchResults] = useState<PatientSummary[] | null>(null);
  const [selectedPatient, setSelectedPatient] = useState<{ patient_id: string; name: string } | null>(initialPatient);
  const [isSearchingPatient, setIsSearchingPatient] = useState(false);
  const [isCreatingPatient, setIsCreatingPatient] = useState(false);
  const [patientError, setPatientError] = useState<string | null>(null);
  const [documentType, setDocumentType] = useState<string>(DOCUMENT_TYPE_OPTIONS[0]?.value ?? '');
  const [recordDate, setRecordDate] = useState<string>(() => todayDateString());
  const [recordTime, setRecordTime] = useState<string>('');
  const [submitError, setSubmitError] = useState<string | null>(null);

  useEffect(() => {
    if (isOpen) {
      // 弹窗打开时:如果有 initialPatient,预填姓名和已选择
      if (initialPatient) {
        setPatientName(initialPatient.name);
        setSelectedPatient({ patient_id: initialPatient.patient_id, name: initialPatient.name });
        setSearchResults(null);
        setPatientError(null);
      } else {
        setPatientName('');
        setSearchResults(null);
        setSelectedPatient(null);
        setIsSearchingPatient(false);
        setIsCreatingPatient(false);
        setPatientError(null);
        setDocumentType(DOCUMENT_TYPE_OPTIONS[0]?.value ?? '');
        setRecordDate(todayDateString());
        setRecordTime('');
        setSubmitError(null);
      }
    } else {
      // 弹窗关闭时:重置所有状态
      setPatientName('');
      setSearchResults(null);
      setSelectedPatient(null);
      setIsSearchingPatient(false);
      setIsCreatingPatient(false);
      setPatientError(null);
      setDocumentType(DOCUMENT_TYPE_OPTIONS[0]?.value ?? '');
      setRecordDate(todayDateString());
      setRecordTime('');
      setSubmitError(null);
    }
  }, [isOpen, initialPatient]);

  const exactNameMatches = useMemo(() => {
    if (!searchResults) return [];
    const trimmed = patientName.trim();
    if (!trimmed) return [];
    return searchResults.filter((patient) => patient.name === trimmed);
  }, [patientName, searchResults]);

  if (!isOpen) return null;

  async function handleSearchPatient() {
    const trimmed = patientName.trim();
    setPatientError(null);
    setSelectedPatient(null);
    if (!trimmed) {
      setPatientError('请输入患者姓名后再搜索');
      setSearchResults(null);
      return;
    }
    setIsSearchingPatient(true);
    try {
      const patients = await getPatients(trimmed);
      setSearchResults(patients);
    } catch (error) {
      setPatientError(getApiErrorMessage(error, '患者搜索失败，请重试'));
      setSearchResults(null);
    } finally {
      setIsSearchingPatient(false);
    }
  }

  function handleSelectExistingPatient(patient: PatientSummary) {
    setSelectedPatient({ patient_id: patient.patient_id, name: patient.name });
    setPatientError(null);
  }

  async function handleCreatePatient() {
    const trimmed = patientName.trim();
    if (!trimmed) {
      setPatientError('请输入患者姓名后再新建');
      return;
    }
    setIsCreatingPatient(true);
    setPatientError(null);
    try {
      const created = await createPatient({ name: trimmed });
      setSelectedPatient({ patient_id: created.patient_id, name: created.name });
      setSearchResults([
        {
          ...created,
          task_count: 0,
          latest_record_at: null
        }
      ]);
    } catch (error) {
      setPatientError(getApiErrorMessage(error, '新建患者失败，请重试'));
    } finally {
      setIsCreatingPatient(false);
    }
  }

  async function handleSubmit(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setSubmitError(null);
    if (!selectedPatient) {
      setSubmitError('请先选择或新建患者');
      return;
    }
    if (!documentType) {
      setSubmitError('请选择记录类型');
      return;
    }
    if (!recordDate) {
      setSubmitError('请填写记录日期');
      return;
    }
    try {
      const payload: CreateTaskInput = {
        patient_id: selectedPatient.patient_id,
        document_type: documentType,
        record_date: recordDate
      };
      // 仅在用户填写时间时附加,避免后端把空串当成非法时间字符串
      if (recordTime) {
        payload.record_time = recordTime;
      }
      await onSubmit(payload);
    } catch (error) {
      setSubmitError(getApiErrorMessage(error, '创建任务失败，请重试'));
    }
  }

  const showAlternateCreate = exactNameMatches.length > 0 && !selectedPatient;
  const submitDisabled =
    isSubmitting ||
    isCreatingPatient ||
    isSearchingPatient ||
    !selectedPatient ||
    !documentType ||
    !recordDate;

  return (
    <div className="qr-dialog-backdrop" role="presentation" onMouseDown={isSubmitting ? undefined : onClose}>
      <section
        className="qr-dialog create-task-dialog"
        role="dialog"
        aria-modal="true"
        aria-label="新建任务"
        aria-labelledby="create-task-dialog-title"
        onMouseDown={(event) => event.stopPropagation()}
      >
        <header className="qr-dialog__header">
          <h2 id="create-task-dialog-title">新建任务</h2>
          <IconButton label="关闭弹窗" onClick={onClose} variant="soft" disabled={isSubmitting}>
            x
          </IconButton>
        </header>

        <form className="create-task-form" onSubmit={handleSubmit}>
          <fieldset className="create-task-fieldset">
            <legend>患者归属</legend>
            <label className="create-task-field">
              <span>患者姓名</span>
              <input
                type="text"
                value={patientName}
                onChange={(event) => {
                  setPatientName(event.currentTarget.value);
                  setSelectedPatient(null);
                  setSearchResults(null);
                }}
                placeholder="输入患者姓名"
                autoComplete="off"
              />
            </label>
            <div className="create-task-actions">
              <button
                type="button"
                className="secondary-action"
                disabled={isSearchingPatient || !patientName.trim()}
                onClick={() => void handleSearchPatient()}
              >
                {isSearchingPatient ? '搜索中' : '搜索患者'}
              </button>
            </div>

            {patientError ? (
              <p className="inline-error" role="alert">
                {patientError}
              </p>
            ) : null}

            {searchResults && searchResults.length === 0 ? (
              <div className="create-task-empty">
                <p>未找到匹配的患者</p>
                <button
                  type="button"
                  className="secondary-action"
                  disabled={isCreatingPatient}
                  onClick={() => void handleCreatePatient()}
                >
                  {isCreatingPatient ? '正在新建' : '新建患者'}
                </button>
              </div>
            ) : null}

            {searchResults && searchResults.length > 0 ? (
              <ul className="create-task-patient-list" aria-label="患者搜索结果">
                {searchResults.map((patient) => {
                  const isSelected = selectedPatient?.patient_id === patient.patient_id;
                  return (
                    <li key={patient.patient_id} className="create-task-patient-row">
                      <div className="create-task-patient-meta">
                        <strong>{patient.patient_id}</strong>
                        <span>{patient.name}</span>
                        <span>{patient.task_count} 个任务 · {patient.latest_record_at ?? '暂无记录'}</span>
                      </div>
                      <button
                        type="button"
                        className={isSelected ? 'primary-action' : 'secondary-action'}
                        onClick={() => handleSelectExistingPatient(patient)}
                      >
                        {isSelected ? '已选择' : `选择 ${patient.patient_id}`}
                      </button>
                    </li>
                  );
                })}
              </ul>
            ) : null}

            {showAlternateCreate ? (
              <div className="create-task-alternate">
                <p>该姓名已存在相同患者，确认是否需要新建独立患者档案。</p>
                <button
                  type="button"
                  className="secondary-action"
                  disabled={isCreatingPatient}
                  onClick={() => void handleCreatePatient()}
                >
                  {isCreatingPatient ? '正在新建' : '仍然新建'}
                </button>
              </div>
            ) : null}

            {selectedPatient ? (
              <div className="create-task-selected" role="status">
                <strong>{selectedPatient.name}</strong>
              </div>
            ) : null}
          </fieldset>

          <fieldset className="create-task-fieldset">
            <legend>记录信息</legend>
            <label className="create-task-field">
              <span>记录类型</span>
              <select
                value={documentType}
                onChange={(event) => setDocumentType(event.currentTarget.value)}
              >
                {DOCUMENT_TYPE_OPTIONS.map((option) => (
                  <option key={option.value} value={option.value}>
                    {option.label}
                  </option>
                ))}
              </select>
            </label>
            <label className="create-task-field">
              <span>记录日期</span>
              <input
                type="date"
                value={recordDate}
                onChange={(event) => setRecordDate(event.currentTarget.value)}
                required
              />
            </label>
            <label className="create-task-field">
              <span>记录时间（可选）</span>
              <input
                type="time"
                value={recordTime}
                onChange={(event) => setRecordTime(event.currentTarget.value)}
              />
            </label>
            <div className="create-task-summary" aria-label="记录选择">
              <span>{DOCUMENT_TYPE_OPTIONS.find((option) => option.value === documentType)?.label ?? '记录类型'}</span>
              <span>{recordDate || '未填日期'}</span>
              <span>{recordTime || '无具体时间'}</span>
            </div>
          </fieldset>

          {submitError ? (
            <p className="inline-error" role="alert">
              {submitError}
            </p>
          ) : null}

          <footer className="create-task-footer">
            <button type="button" className="ghost-action" onClick={onClose} disabled={isSubmitting}>
              取消
            </button>
            <button type="submit" className="primary-action" disabled={submitDisabled}>
              {isSubmitting ? '正在创建' : '创建任务'}
            </button>
          </footer>
        </form>
      </section>
    </div>
  );
}
