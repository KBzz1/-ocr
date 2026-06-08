import { useState } from 'react';

import { getApiErrorMessage } from '../../api/client';
import { deletePatient } from '../../api/patients';
import { IconButton } from '../common/IconButton';

type DeletePatientDialogProps = {
  isOpen: boolean;
  patientId: string;
  patientName: string;
  hasProcessingTasks?: boolean;
  onClose: () => void;
  onDeleted: () => void;
};

export function DeletePatientDialog({
  isOpen,
  patientId,
  patientName,
  hasProcessingTasks = false,
  onClose,
  onDeleted
}: DeletePatientDialogProps) {
  const [isDeletingOnly, setIsDeletingOnly] = useState(false);
  const [isDeletingAll, setIsDeletingAll] = useState(false);
  const [error, setError] = useState<string | null>(null);

  if (!isOpen) return null;

  async function handleDeleteOnly() {
    setIsDeletingOnly(true);
    setError(null);
    try {
      await deletePatient(patientId, false);
      onDeleted();
    } catch (deleteError: unknown) {
      setError(getApiErrorMessage(deleteError, '删除患者失败,请重试'));
    } finally {
      setIsDeletingOnly(false);
    }
  }

  async function handleDeleteAll() {
    setIsDeletingAll(true);
    setError(null);
    try {
      await deletePatient(patientId, true);
      onDeleted();
    } catch (deleteError: unknown) {
      setError(getApiErrorMessage(deleteError, '删除患者失败,请重试'));
    } finally {
      setIsDeletingAll(false);
    }
  }

  const isBusy = isDeletingOnly || isDeletingAll;

  return (
    <div className="qr-dialog-backdrop" role="presentation" onMouseDown={isBusy ? undefined : onClose}>
      <section
        className="qr-dialog delete-patient-dialog"
        role="dialog"
        aria-modal="true"
        aria-label="删除患者"
        aria-labelledby="delete-patient-dialog-title"
        onMouseDown={(event) => event.stopPropagation()}
      >
        <header className="qr-dialog__header">
          <h2 id="delete-patient-dialog-title">删除患者</h2>
          <IconButton label="关闭弹窗" onClick={onClose} variant="soft" disabled={isBusy}>
            x
          </IconButton>
        </header>
        <div className="delete-patient-dialog__body">
          <div className="delete-patient-dialog__summary">
            <strong>{patientName}</strong>
            <span>{patientId}</span>
          </div>
          {hasProcessingTasks ? (
            <p className="delete-patient-dialog__warning" role="note">
              有任务处理中，不能同时删除任务。
            </p>
          ) : null}
          <div className="delete-patient-dialog__options">
            <button
              type="button"
              className="delete-patient-option"
              aria-label="仅删除患者"
              onClick={() => void handleDeleteOnly()}
              disabled={isBusy}
            >
              <strong>{isDeletingOnly ? '删除中' : '仅删除患者'}</strong>
              <span>任务保留，可改绑</span>
            </button>
            <button
              type="button"
              className="delete-patient-option delete-patient-option--danger"
              aria-label="患者和任务都删除"
              onClick={() => void handleDeleteAll()}
              disabled={isBusy}
            >
              <strong>{isDeletingAll ? '删除中' : '患者和任务都删除'}</strong>
              <span>任务列表隐藏</span>
            </button>
          </div>
          {error ? (
            <p className="inline-error" role="alert">{error}</p>
          ) : null}
        </div>
        <footer className="qr-dialog__footer">
          <button type="button" className="ghost-action" onClick={onClose} disabled={isBusy}>
            取消
          </button>
        </footer>
      </section>
    </div>
  );
}
