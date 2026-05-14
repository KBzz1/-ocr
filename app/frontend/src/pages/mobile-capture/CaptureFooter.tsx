interface CaptureFooterProps {
  disabled: boolean;
  isFinishing: boolean;
  canFinish: boolean;
  onCaptureNext: () => void;
  onFinish: () => void;
}

export function CaptureFooter({
  disabled,
  isFinishing,
  canFinish,
  onCaptureNext,
  onFinish
}: CaptureFooterProps) {
  return (
    <footer className="capture-footer" role="contentinfo">
      <button className="mobile-button secondary" type="button" disabled={disabled} onClick={onCaptureNext}>
        继续拍下一页
      </button>
      <button
        className="mobile-button"
        type="button"
        disabled={disabled || isFinishing || !canFinish}
        onClick={onFinish}
      >
        {isFinishing ? '提交中' : '完成采集'}
      </button>
    </footer>
  );
}
