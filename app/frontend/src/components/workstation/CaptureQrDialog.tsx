import type { CaptureSessionSummary } from '../../pages/workstation/workstation.types';
import { IconButton } from '../common/IconButton';

type CaptureQrDialogProps = {
  isOpen: boolean;
  session: CaptureSessionSummary | null;
  onClose: () => void;
  onRegenerate: () => void;
};

export function CaptureQrDialog({ isOpen, session, onClose, onRegenerate }: CaptureQrDialogProps) {
  if (!isOpen) return null;

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
            <div className="qr-placeholder" role="img" aria-label="采集二维码">
              <span className="qr-placeholder__scanline" aria-hidden="true" />
              <svg viewBox="0 0 100 100" aria-hidden="true">
                <path d="M10 10h28v28H10zM16 16v16h16V16zM62 10h28v28H62zM68 16v16h16V16zM10 62h28v28H10zM16 68v16h16V68z" />
                <path d="M47 10h7v18h-7zM47 35h7v12h-7zM10 47h20v7H10zM36 47h20v7H36zM63 47h27v7H63zM47 57h7v23h-7zM60 60h16v7H60zM82 60h8v7h-8zM60 72h7v18h-7zM72 72h18v7H72zM72 84h7v6h-7zM84 82h6v8h-6z" />
              </svg>
            </div>
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
          <button className="link-action" type="button">
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
