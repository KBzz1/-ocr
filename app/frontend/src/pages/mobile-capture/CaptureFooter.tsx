interface CaptureFooterProps {
  canFinish: boolean;
  isFinishing: boolean;
  canReset?: boolean;
  onFinish: () => void;
  onReset?: () => void;
}

export function CaptureFooter({
  canFinish,
  isFinishing,
  canReset = false,
  onFinish,
  onReset
}: CaptureFooterProps) {
  return (
    <footer className="capture-footer" role="contentinfo">
      <button
        className="mobile-button secondary"
        type="button"
        disabled={!canReset || isFinishing}
        onClick={onReset}
      >
        清除所有图片
      </button>
      <button
        className="mobile-button"
        type="button"
        disabled={!canFinish || isFinishing}
        onClick={onFinish}
      >
        {isFinishing ? '提交中' : '完成上传'}
      </button>
    </footer>
  );
}
