import type { BatchExcelTemplate } from '../../api/export';

type BatchExcelExportDialogProps = {
  isOpen: boolean;
  templates: BatchExcelTemplate[];
  selectedDocumentType: string;
  isExporting: boolean;
  onSelectTemplate: (documentType: string) => void;
  onConfirm: () => void;
  onClose: () => void;
};

export function BatchExcelExportDialog({
  isOpen,
  templates,
  selectedDocumentType,
  isExporting,
  onSelectTemplate,
  onConfirm,
  onClose
}: BatchExcelExportDialogProps) {
  if (!isOpen) return null;
  return (
    <div
      className="batch-excel-dialog-overlay"
      role="presentation"
      onMouseDown={(event) => {
        if (event.target === event.currentTarget) onClose();
      }}
    >
      <div className="batch-excel-dialog" role="dialog" aria-modal="true" aria-label="全部导出 Excel">
        <h2 className="batch-excel-dialog__title">全部导出 Excel</h2>
        <p className="batch-excel-dialog__hint">选择记录模板，该模板全部已完成记录将导出到同一张表</p>
        {templates.length === 0 ? (
          <p className="batch-excel-dialog__empty">暂无可导出的记录模板</p>
        ) : (
          <div className="batch-excel-dialog__templates" role="radiogroup" aria-label="记录模板">
            {templates.map((template) => (
              <label key={template.document_type} className="batch-excel-dialog__template">
                <input
                  type="radio"
                  name="batch-excel-template"
                  value={template.document_type}
                  checked={selectedDocumentType === template.document_type}
                  onChange={() => onSelectTemplate(template.document_type)}
                />
                {template.label}
              </label>
            ))}
          </div>
        )}
        <div className="batch-excel-dialog__actions">
          <button type="button" className="batch-excel-dialog__cancel" onClick={onClose} disabled={isExporting}>
            取消
          </button>
          <button
            type="button"
            className="batch-excel-dialog__confirm"
            disabled={isExporting || templates.length === 0 || !selectedDocumentType}
            onClick={onConfirm}
          >
            {isExporting ? '导出中' : '确认导出'}
          </button>
        </div>
      </div>
    </div>
  );
}
