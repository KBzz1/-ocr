interface CaptureFooterProps {
  canFinish: boolean;
  isFinishing: boolean;
  onFinish: () => void;
}

export function CaptureFooter({
  canFinish,
  isFinishing,
  onFinish
}: CaptureFooterProps) {
  return (
    <footer className="capture-footer" role="contentinfo">
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
