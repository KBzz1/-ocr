import { useEffect, useState } from 'react';
import QRCode from 'qrcode';

import type { CaptureSessionSummary } from '../../pages/workstation/workstation.types';
import { IconButton } from '../common/IconButton';

type CaptureQrDialogProps = {
  isOpen: boolean;
  session: CaptureSessionSummary | null;
  onClose: () => void;
  onRegenerate: () => void;
};

export function CaptureQrDialog({ isOpen, session, onClose, onRegenerate }: CaptureQrDialogProps) {
  const [qrSvgDataUrl, setQrSvgDataUrl] = useState<string | null>(null);
  const [isHelpOpen, setIsHelpOpen] = useState(false);
  const [copyStatus, setCopyStatus] = useState<string | null>(null);

  useEffect(() => {
    let isCurrent = true;
    setQrSvgDataUrl(null);

    if (!isOpen || !session?.qrCodeValue) return undefined;

    QRCode.toString(session.qrCodeValue, {
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
  }, [isOpen, session?.qrCodeValue]);

  useEffect(() => {
    if (!isOpen) {
      setIsHelpOpen(false);
      setCopyStatus(null);
    }
  }, [isOpen]);

  if (!isOpen) return null;

  async function handleCopyLink() {
    if (!session?.qrCodeValue) return;

    try {
      await navigator.clipboard?.writeText(session.qrCodeValue);
      setCopyStatus('已复制');
    } catch {
      setCopyStatus('复制失败，请手动选择链接');
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
            <p className="section-kicker">扫码采集</p>
            <h2 id="qr-dialog-title">采集二维码</h2>
          </div>
          <IconButton label="关闭弹窗" onClick={onClose} variant="soft">
            x
          </IconButton>
        </header>

        <div className="qr-dialog__body">
          <div className="qr-dialog__scan">
            <p>请使用手机浏览器扫描二维码进行拍照采集。</p>
            <div className="qr-dialog__notice">
              手机需与电脑处于同一网络环境，无法连接时请查看帮助说明。
            </div>
            {qrSvgDataUrl ? (
              <img className="qr-code-image" src={qrSvgDataUrl} alt="采集二维码" />
            ) : (
              <div className="qr-code-frame" aria-live="polite">二维码生成中</div>
            )}
            <button className="secondary-action" type="button" onClick={onRegenerate}>
              重新生成二维码
            </button>
          </div>

          <div className="qr-dialog__status">
            <div className="qr-status-row qr-status-row--success">
              <strong>服务已就绪</strong>
              <span>本地采集服务正常</span>
            </div>
            <div className="qr-status-row qr-status-row--info">
              <strong>{session ? '等待设备扫码' : '等待新会话'}</strong>
              <span>剩余有效时间 {session?.remainingTimeText ?? '30 分钟'}</span>
            </div>
            <div className="qr-status-row">
              <strong>图像传输</strong>
              <span>已上传页数 {session?.uploadedPages ?? 0} 页</span>
            </div>
          </div>
        </div>

        <footer className="qr-dialog__footer">
          {isHelpOpen && session?.qrCodeValue ? (
            <div className="qr-help-panel">
              <label htmlFor="mobile-capture-url">手机访问链接</label>
              <div className="qr-help-panel__copy-row">
                <input id="mobile-capture-url" value={session.qrCodeValue} readOnly />
                <button className="secondary-action" type="button" onClick={() => void handleCopyLink()}>
                  复制链接
                </button>
              </div>
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
