import { useEffect, useState } from 'react';
import QRCode from 'qrcode';

import captureIllustration from '../../assets/illustrations/phone-qr-capture.png';
import type { CaptureSessionSummary } from '../../pages/workstation/workstation.types';
import { IconButton } from '../common/IconButton';

type CaptureQrDialogProps = {
  isOpen: boolean;
  session: CaptureSessionSummary | null;
  onClose: () => void;
  onRegenerate: () => void;
  lanAddresses?: string[];
};

export function CaptureQrDialog({ isOpen, session, onClose, onRegenerate, lanAddresses = [] }: CaptureQrDialogProps) {
  const [qrSvgDataUrl, setQrSvgDataUrl] = useState<string | null>(null);
  const [isHelpOpen, setIsHelpOpen] = useState(false);
  const [copyStatus, setCopyStatus] = useState<string | null>(null);
  const [manualUrl, setManualUrl] = useState('');
  const [qrValueOverride, setQrValueOverride] = useState<string | null>(null);
  const [manualUrlError, setManualUrlError] = useState<string | null>(null);
  const qrValue = qrValueOverride ?? session?.qrCodeValue ?? '';

  useEffect(() => {
    let isCurrent = true;
    setQrSvgDataUrl(null);

    if (!isOpen || !qrValue) return undefined;

    QRCode.toString(qrValue, {
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
  }, [isOpen, qrValue]);

  useEffect(() => {
    if (isOpen) {
      setQrValueOverride(null);
      setManualUrl(session?.qrCodeValue ?? '');
      setManualUrlError(null);
    }
  }, [isOpen, session?.qrCodeValue]);

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

  function buildUrlForAddress(address: string) {
    if (!session) return '';
    return `http://${address}/mobile/sessions/${encodeURIComponent(session.id)}`;
  }

  function applyManualUrl() {
    try {
      const parsed = new URL(manualUrl);
      if (!['http:', 'https:'].includes(parsed.protocol)) {
        throw new Error('invalid protocol');
      }
      setQrValueOverride(parsed.toString());
      setManualUrlError(null);
    } catch {
      setManualUrlError('请输入有效的手机访问链接');
    }
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
            <h2 id="qr-dialog-title">采集二维码</h2>
          </div>
          <IconButton label="关闭弹窗" onClick={onClose} variant="soft">
            x
          </IconButton>
        </header>

        <div className="qr-dialog__body">
          <div className="qr-dialog__scan">
            {qrSvgDataUrl ? (
              <div className="qr-code-shell">
                <span className="qr-code-corner qr-code-corner--tl" />
                <span className="qr-code-corner qr-code-corner--tr" />
                <span className="qr-code-corner qr-code-corner--bl" />
                <span className="qr-code-corner qr-code-corner--br" />
                <img
                  className="qr-code-image"
                  src={qrSvgDataUrl}
                  alt="采集二维码"
                  data-qr-value={qrValue}
                />
              </div>
            ) : (
              <div className="qr-code-frame" aria-live="polite">二维码生成中</div>
            )}
            <button className="secondary-action" type="button" onClick={onRegenerate}>
              重新生成二维码
            </button>
          </div>

          <img className="qr-dialog__illustration" src={captureIllustration} alt="" aria-hidden="true" />

          <div className="qr-dialog__status">
            <div className="qr-status-row qr-status-row--success">
              <span className="qr-status-icon" aria-hidden="true">✓</span>
              <div>
                <strong>会话已创建</strong>
                <span>{session?.createdAtText ?? '等待扫码'}</span>
              </div>
            </div>
            <div className="qr-status-row qr-status-row--info">
              <span className="qr-status-icon" aria-hidden="true">◷</span>
              <div>
                <strong>剩余 {session?.remainingTimeText ?? '30 分钟'}</strong>
                <span>到期后自动失效</span>
              </div>
            </div>
            <div className="qr-status-row">
              <span className="qr-status-icon" aria-hidden="true">↑</span>
              <div>
                <strong>已上传 {session?.uploadedPages ?? 0} 页</strong>
                <span>等待手机上传页面</span>
              </div>
            </div>
          </div>
        </div>

        <footer className="qr-dialog__footer">
          {isHelpOpen && session?.qrCodeValue ? (
            <div className="qr-help-panel">
              <label htmlFor="mobile-capture-url">手机访问链接</label>
              <div className="qr-help-panel__copy-row">
                <input
                  id="mobile-capture-url"
                  aria-label="手机访问链接"
                  value={manualUrl}
                  onChange={(event) => setManualUrl(event.currentTarget.value)}
                />
                <button className="secondary-action" type="button" onClick={() => void handleCopyLink()}>
                  复制链接
                </button>
              </div>
              {lanAddresses.length > 0 ? (
                <div className="qr-help-panel__addresses" aria-label="局域网地址列表">
                  {lanAddresses.map((address) => (
                    <button
                      className="secondary-action"
                      key={address}
                      type="button"
                      onClick={() => {
                        const nextUrl = buildUrlForAddress(address);
                        setManualUrl(nextUrl);
                        setQrValueOverride(nextUrl);
                        setManualUrlError(null);
                      }}
                    >
                      {address}
                    </button>
                  ))}
                </div>
              ) : null}
              <button className="secondary-action" type="button" onClick={applyManualUrl}>
                更新二维码
              </button>
              {manualUrlError ? <span role="alert">{manualUrlError}</span> : null}
              <p>请确认手机与电脑连接同一局域网或电脑热点，再在手机浏览器打开此链接。</p>
              {copyStatus ? <span role="status">{copyStatus}</span> : null}
            </div>
          ) : null}
          <button className="link-action" type="button" onClick={() => setIsHelpOpen((value) => !value)}>
            手机无法连接？
          </button>
          <button className="secondary-action" type="button" onClick={onClose}>
            关闭
          </button>
        </footer>
      </section>
    </div>
  );
}
