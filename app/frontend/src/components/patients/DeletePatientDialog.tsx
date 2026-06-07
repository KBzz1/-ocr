import { useState } from 'react';

import { ApiError } from '../../api/client';
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

function getApiMessage(error: unknown, fallback: string) {
  return error instanceof ApiError ? error.message : fallback;
}

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
      setError(getApiMessage(deleteError, '删除患者失败,请重试'));
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
      setError(getApiMessage(deleteError, '删除患者失败,请重试'));
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
          <p>
            患者 <strong>{patientName}</strong>({patientId})的归档与关联任务有下列两个选项。
            所有删除均为逻辑删除,任务文件、OCR 文本和字段结果将完整保留。
          </p>
          {hasProcessingTasks ? (
            <p className="delete-patient-dialog__warning" role="note">
              当前存在处理中的任务,选择"同时删除患者及关联任务"会被后端拒绝,请等待处理完成或先取消。
            </p>
          ) : null}
          <ul className="delete-patient-dialog__options">
            <li>
              <strong>仅删除患者</strong>
              <span>患者档案从患者管理移除;关联任务保留,在任务管理显示"患者已删除",仍可改绑。</span>
            </li>
            <li>
              <strong>同时删除患者及关联任务</strong>
              <span>患者与所有关联任务同时逻辑删除;默认列表不再显示;首版不提供恢复入口。</span>
            </li>
          </ul>
          {error ? (
            <p className="inline-error" role="alert">{error}</p>
          ) : null}
        </div>
        <footer className="qr-dialog__footer">
          <button type="button" className="ghost-action" onClick={onClose} disabled={isBusy}>
            取消
          </button>
          <button
            type="button"
            className="secondary-action"
            onClick={() => void handleDeleteOnly()}
            disabled={isBusy}
          >
            {isDeletingOnly ? '删除中' : '仅删除患者'}
          </button>
          <button
            type="button"
            className="warning-action"
            onClick={() => void handleDeleteAll()}
            disabled={isBusy}
          >
            {isDeletingAll ? '删除中' : '同时删除患者及关联任务'}
          </button>
        </footer>
      </section>
    </div>
  );
}
