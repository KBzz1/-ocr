import { useEffect, useState } from 'react';
import QRCode from 'qrcode';

import type { TaskUploadSummary } from '../../pages/workstation/workstation.types';
import { IconButton } from '../common/IconButton';

type CaptureQrDialogProps = {
  isOpen: boolean;
  task: TaskUploadSummary | null;
  onClose: () => void;
  lanAddresses?: string[];
};

function appendQrRefreshParam(value: string, version: number) {
  if (version === 0) return value;

  try {
    const parsed = new URL(value);
    parsed.searchParams.set('qr_refresh', String(version));
    return parsed.toString();
  } catch {
    const separator = value.includes('?') ? '&' : '?';
    return `${value}${separator}qr_refresh=${version}`;
  }
}

function hostFromMobileUrl(value: string) {
  try {
    return new URL(value).host;
  } catch {
    return '';
  }
}

function normalizeHostInput(value: string) {
  const trimmed = value.trim();
  if (!trimmed) return '';

  try {
    return new URL(trimmed).host;
  } catch {
    return trimmed.replace(/^https?:\/\//i, '').replace(/\/.*$/, '');
  }
}

function buildMobileUrlWithHost(value: string, hostInput: string) {
  const normalizedHost = normalizeHostInput(hostInput);
  if (!normalizedHost) return value;

  try {
    const parsed = new URL(value);
    parsed.host = normalizedHost.includes(':') ? normalizedHost : `${normalizedHost}:${parsed.port || '8081'}`;
    return parsed.toString();
  } catch {
    return value;
  }
}

export function CaptureQrDialog({ isOpen, task, onClose }: CaptureQrDialogProps) {
  const [qrSvgDataUrl, setQrSvgDataUrl] = useState<string | null>(null);
  const [qrVersion, setQrVersion] = useState(0);
  const [isHelpOpen, setIsHelpOpen] = useState(false);
  const [copyStatus, setCopyStatus] = useState<string | null>(null);
  const [mobileHostInput, setMobileHostInput] = useState('');
  const baseQrValue = task?.mobile_upload_url ?? '';
  const qrValue = baseQrValue ? buildMobileUrlWithHost(baseQrValue, mobileHostInput) : '';
  const qrRenderValue = qrValue ? appendQrRefreshParam(qrValue, qrVersion) : '';

  useEffect(() => {
    let isCurrent = true;
    setQrSvgDataUrl(null);

    if (!isOpen || !qrRenderValue) return undefined;

    QRCode.toString(qrRenderValue, {
      type: 'svg',
      margin: 1,
      width: 192,
      color: {
        dark: '#0f172a',
        light: '#ffffff'
      }
    }).then((svg) => {
      if (isCurrent) {
        setQrSvgDataUrl(`data:image/svg+xml;utf8,${encodeURIComponent(svg)}`);
      }
    });

    return () => {
      isCurrent = false;
    };
  }, [isOpen, qrRenderValue]);

  useEffect(() => {
    if (isOpen) {
      setMobileHostInput(hostFromMobileUrl(task?.mobile_upload_url ?? ''));
      setQrVersion(0);
    }
  }, [isOpen, task?.mobile_upload_url]);

  useEffect(() => {
    if (!isOpen) {
      setIsHelpOpen(false);
      setCopyStatus(null);
    }
  }, [isOpen]);

  if (!isOpen) return null;

  async function handleCopyLink() {
    if (!qrValue) return;

    try {
      await navigator.clipboard?.writeText(qrValue);
      setCopyStatus('已复制');
    } catch {
      setCopyStatus('复制失败，请手动选择链接');
    }
  }

  function handleRegenerateQr() {
    setQrVersion((version) => version + 1);
  }

  return (
    <div className="qr-dialog-backdrop" role="presentation" onMouseDown={onClose}>
      <section
        className="qr-dialog"
        role="dialog"
        aria-modal="true"
        aria-labelledby="qr-dialog-title"
        onMouseDown={(event) => event.stopPropagation()}
      >
        <header className="qr-dialog__header">
          <div>
            <h2 id="qr-dialog-title">手机扫码上传</h2>
          </div>
          <IconButton label="关闭弹窗" onClick={onClose} variant="soft">
            x
          </IconButton>
        </header>

        <div className="qr-dialog__body">
          <div className="qr-dialog__task-summary" aria-label="任务信息">
            <div>
              <span>患者</span>
              <strong>{task?.patient?.name ?? '未命名患者'}</strong>
            </div>
            <div>
              <span>记录类型</span>
              <strong>{task?.document_type_label ?? task?.document_type ?? '入院记录'}</strong>
            </div>
            <div>
              <span>任务</span>
              <strong>{task?.display_name ?? task?.task_id ?? '-'}</strong>
            </div>
          </div>
          {qrSvgDataUrl ? (
            <div className="qr-code-shell">
              <img
                className="qr-code-image"
                src={qrSvgDataUrl}
                alt="任务上传二维码"
                data-qr-value={qrRenderValue}
              />
            </div>
          ) : (
            <div className="qr-code-frame" aria-live="polite">二维码生成中</div>
          )}
          <div className="qr-dialog__upload-state" aria-live="polite">
            <strong>等待手机上传图片</strong>
            <span>已上传 {task?.uploadedPages ?? 0} 张</span>
          </div>
        </div>

        <footer className="qr-dialog__footer">
          {isHelpOpen && task?.mobile_upload_url ? (
            <div className="qr-help-panel">
              <label htmlFor="mobile-capture-host">电脑 IPv4 或访问地址</label>
              <input
                id="mobile-capture-host"
                aria-label="电脑 IPv4 或访问地址"
                value={mobileHostInput}
                placeholder="例如 192.168.1.5"
                onChange={(event) => {
                  setMobileHostInput(event.currentTarget.value);
                  setCopyStatus(null);
                }}
              />
              <label htmlFor="mobile-capture-url">手机访问链接</label>
              <div className="qr-help-panel__copy-row">
                <input
                  id="mobile-capture-url"
                  aria-label="手机访问链接"
                  value={qrValue}
                  readOnly
                />
                <button className="secondary-action qr-help-panel__copy-button" type="button" onClick={() => void handleCopyLink()}>
                  复制链接
                </button>
              </div>
              <p>按 Windows 设置中的 IPv4 修改后，二维码会同步更新。</p>
              {copyStatus ? <span role="status">{copyStatus}</span> : null}
            </div>
          ) : null}
          <div className="qr-dialog__footer-actions">
            <button className="ghost-action qr-dialog__regenerate" type="button" onClick={handleRegenerateQr}>
              重新生成二维码
            </button>
            <button className="link-action qr-dialog__help-toggle" type="button" onClick={() => setIsHelpOpen((value) => !value)}>
              手机无法连接？
            </button>
          </div>
        </footer>
      </section>
    </div>
  );
}
