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

export function CaptureQrDialog({ isOpen, task, onClose }: CaptureQrDialogProps) {
  const [qrSvgDataUrl, setQrSvgDataUrl] = useState<string | null>(null);
  const [qrVersion, setQrVersion] = useState(0);
  const [isHelpOpen, setIsHelpOpen] = useState(false);
  const [copyStatus, setCopyStatus] = useState<string | null>(null);
  const [manualUrl, setManualUrl] = useState('');
  const qrValue = task?.mobile_upload_url ?? '';
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
      setManualUrl(task?.mobile_upload_url ?? '');
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
            <h2 id="qr-dialog-title">任务上传二维码</h2>
          </div>
          <IconButton label="关闭弹窗" onClick={onClose} variant="soft">
            x
          </IconButton>
        </header>

        <div className="qr-dialog__body">
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
          <button className="secondary-action qr-dialog__regenerate" type="button" onClick={handleRegenerateQr}>
            重新生成二维码
          </button>
        </div>

        <footer className="qr-dialog__footer">
          {isHelpOpen && task?.mobile_upload_url ? (
            <div className="qr-help-panel">
              <label htmlFor="mobile-capture-url">手机访问链接</label>
              <div className="qr-help-panel__copy-row">
                <input
                  id="mobile-capture-url"
                  aria-label="手机访问链接"
                  value={manualUrl}
                  onChange={(event) => setManualUrl(event.currentTarget.value)}
                />
                <button className="secondary-action qr-help-panel__copy-button" type="button" onClick={() => void handleCopyLink()}>
                  复制链接
                </button>
              </div>
              <p>请确认手机与电脑连接同一局域网或电脑热点，再在手机浏览器打开此链接。</p>
              {copyStatus ? <span role="status">{copyStatus}</span> : null}
            </div>
          ) : null}
          <button className="link-action qr-dialog__help-toggle" type="button" onClick={() => setIsHelpOpen((value) => !value)}>
            手机无法连接？
          </button>
        </footer>
      </section>
    </div>
  );
}
