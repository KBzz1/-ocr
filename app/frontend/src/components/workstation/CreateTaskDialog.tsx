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

type CreateTaskStep = 'patient' | 'record';

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
  const [currentStep, setCurrentStep] = useState<CreateTaskStep>(initialPatient ? 'record' : 'patient');
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
        setCurrentStep('record');
        setSearchResults(null);
        setPatientError(null);
      } else {
        setPatientName('');
        setSearchResults(null);
        setSelectedPatient(null);
        setCurrentStep('patient');
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
      setCurrentStep('patient');
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
      setCurrentStep('record');
    } catch (error) {
      setPatientError(getApiErrorMessage(error, '新建患者失败，请重试'));
    } finally {
      setIsCreatingPatient(false);
    }
  }

  async function handleSubmit(event?: React.FormEvent<HTMLFormElement>) {
    event?.preventDefault();
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
  const showPatientEmpty = searchResults && searchResults.length === 0;
  const showPatientResults = searchResults && searchResults.length > 0;
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
          <div className="create-task-steps" aria-label="创建任务步骤">
            <button
              type="button"
              className={`create-task-step${currentStep === 'patient' ? ' is-active' : ''}${
                selectedPatient && currentStep !== 'patient' ? ' is-complete' : ''
              }`}
              onClick={() => selectedPatient && setCurrentStep('patient')}
              disabled={!selectedPatient || isSubmitting}
              aria-label="返回第 1 步：患者"
            >
              <span className="create-task-step__index">1</span>
              <span className="create-task-step__label">患者</span>
            </button>
            <span className="create-task-step__divider" aria-hidden="true" />
            <button
              type="button"
              className={`create-task-step${currentStep === 'record' ? ' is-active' : ''}`}
              aria-label="当前步骤：记录信息"
              aria-current="step"
            >
              <span className="create-task-step__index">2</span>
              <span className="create-task-step__label">记录信息</span>
            </button>
            <span className="create-task-step__divider" aria-hidden="true" />
            <span className="create-task-step create-task-step--upcoming" aria-label="后续步骤：上传">
              <span className="create-task-step__index">3</span>
              <span className="create-task-step__label">上传</span>
            </span>
          </div>

          {currentStep === 'patient' ? (
            <fieldset className="create-task-fieldset create-task-fieldset--plain">
              <legend>选择患者</legend>
              <div className="create-task-search-row">
                <label className="create-task-field create-task-field--search">
                  <span>患者姓名</span>
                  <input
                    type="text"
                    value={patientName}
                    onChange={(event) => {
                      setPatientName(event.currentTarget.value);
                      setSelectedPatient(null);
                      setSearchResults(null);
                    }}
                    placeholder="输入患者姓名或编号"
                    autoComplete="off"
                  />
                </label>
                <button
                  type="button"
                  className="primary-action create-task-search-button"
                  disabled={isSearchingPatient || !patientName.trim()}
                  aria-label="搜索患者"
                  onClick={() => void handleSearchPatient()}
                >
                  <svg
                    aria-hidden="true"
                    width="16"
                    height="16"
                    viewBox="0 0 16 16"
                    fill="none"
                    stroke="currentColor"
                    strokeWidth="1.8"
                    strokeLinecap="round"
                    strokeLinejoin="round"
                  >
                    <circle cx="7" cy="7" r="4.5" />
                    <path d="M10.5 10.5L14 14" />
                  </svg>
                  <span>{isSearchingPatient ? '搜索中' : '搜索'}</span>
                </button>
              </div>

              {patientError ? (
                <p className="inline-error" role="alert">
                  {patientError}
                </p>
              ) : null}

              {showPatientResults ? (
                <>
                  <p className="create-task-patient-summary" role="status">
                    <span>
                      找到 <strong>{searchResults.length}</strong> 位匹配患者
                    </span>
                  </p>
                  <ul className="create-task-patient-list" aria-label="患者搜索结果">
                    {searchResults.map((patient) => {
                      const isSelected = selectedPatient?.patient_id === patient.patient_id;
                      return (
                        <li
                          key={patient.patient_id}
                          className={`create-task-patient-row${isSelected ? ' is-selected' : ''}`}
                        >
                          <button
                            type="button"
                            className="create-task-patient-row__selectable"
                            aria-label={`${isSelected ? '已选择' : '选择'} ${patient.patient_id}`}
                            aria-pressed={isSelected}
                            onClick={() => handleSelectExistingPatient(patient)}
                          >
                            <span
                              className={`create-task-patient-row__radio${isSelected ? ' is-checked' : ''}`}
                              aria-hidden="true"
                            >
                              {isSelected ? <span className="create-task-patient-row__radio-dot" /> : null}
                            </span>
                            <span className="create-task-patient-row__name">{patient.name}</span>
                            <span className="create-task-patient-row__id">{patient.patient_id}</span>
                            <span className="create-task-patient-row__demo">
                              {patient.gender ?? '—'}
                            </span>
                            <span className="create-task-patient-row__demo">
                              {typeof patient.age === 'number' ? `${patient.age}岁` : '—'}
                            </span>
                            <span className="create-task-patient-row__date">
                              {patient.latest_record_at ? `最近记录：${patient.latest_record_at}` : '暂无记录'}
                            </span>
                          </button>
                        </li>
                      );
                    })}
                    <li className="create-task-patient-create">
                      <button
                        type="button"
                        className="ghost-action create-task-patient-create__button"
                        disabled={isCreatingPatient}
                        onClick={() => void handleCreatePatient()}
                      >
                        <span aria-hidden="true">+</span>
                        {isCreatingPatient ? '正在新建' : '仍然新建患者'}
                      </button>
                    </li>
                  </ul>
                </>
              ) : null}

              {showAlternateCreate ? (
                <p className="create-task-alternate-hint" role="note">
                  已存在与「{patientName.trim()}」同名的患者，请先确认是否选择已有档案。
                </p>
              ) : null}

              {showPatientEmpty ? (
                <div className="create-task-empty" role="status">
                  <strong>未找到匹配患者</strong>
                  <button
                    type="button"
                    className="link-action create-task-patient-create__button"
                    disabled={isCreatingPatient}
                    onClick={() => void handleCreatePatient()}
                  >
                    <span aria-hidden="true">+</span>
                    {isCreatingPatient ? '正在新建' : '新建同名患者'}
                  </button>
                </div>
              ) : null}
            </fieldset>
          ) : (
            <fieldset className="create-task-fieldset">
              <legend>记录信息</legend>
              {selectedPatient ? (
                <div className="create-task-selected" role="status">
                  <span className="create-task-selected__chip">
                    <span className="create-task-selected__check" aria-hidden="true" />
                    <strong>{selectedPatient.name}</strong>
                    <span>{selectedPatient.patient_id}</span>
                  </span>
                  <button
                    type="button"
                    className="link-action create-task-selected__reselect"
                    onClick={() => setCurrentStep('patient')}
                    aria-label="返回第 1 步重新选择患者"
                  >
                    重新选择
                  </button>
                </div>
              ) : null}
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
            </fieldset>
          )}

          {submitError ? (
            <p className="inline-error" role="alert">
              {submitError}
            </p>
          ) : null}

          <footer className="create-task-footer">
            {currentStep === 'patient' ? (
              <span className="create-task-footer__summary" aria-live="polite">
                {selectedPatient ? (
                  <>
                    <span className="create-task-footer__summary-label">已选择</span>
                    <span className="create-task-footer__summary-value">
                      {selectedPatient.name} · {selectedPatient.patient_id}
                    </span>
                  </>
                ) : (
                  <span className="create-task-footer__summary-placeholder">尚未选择患者</span>
                )}
              </span>
            ) : (
              <button
                type="button"
                className="ghost-action create-task-footer__back"
                onClick={() => setCurrentStep('patient')}
                disabled={isSubmitting}
              >
                ← 上一步
              </button>
            )}
            <div className="create-task-footer__actions">
              <button type="button" className="ghost-action" onClick={onClose} disabled={isSubmitting}>
                取消
              </button>
              {currentStep === 'patient' ? (
                <button
                  type="button"
                  className="primary-action"
                  disabled={!selectedPatient}
                  data-testid="create-task-next"
                  onClick={() => setCurrentStep('record')}
                >
                  下一步
                </button>
              ) : (
                <button
                  type="button"
                  className="primary-action create-task-footer__submit"
                  disabled={submitDisabled}
                  data-testid="create-task-submit"
                  onClick={() => void handleSubmit()}
                >
                  <span>{isSubmitting ? '正在创建' : '下一步'}</span>
                  <span className="create-task-footer__submit-suffix" aria-hidden="true">上传</span>
                </button>
              )}
            </div>
          </footer>
        </form>
      </section>
    </div>
  );
}
