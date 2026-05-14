import {
  QuadSelector,
  type QuadPointsByCorner
} from '../../components/mobile-capture/QuadSelector';

interface CaptureQuadScreenProps {
  previewUrl?: string;
  quad: QuadPointsByCorner;
  width: number;
  height: number;
  isUploading: boolean;
  confirmLabel: string;
  cancelLabel?: string;
  onChangeQuad: (quad: QuadPointsByCorner) => void;
  onResetQuad: () => void;
  onCancel: () => void;
  onConfirm: () => void;
}

export function CaptureQuadScreen({
  previewUrl,
  quad,
  width,
  height,
  isUploading,
  confirmLabel,
  cancelLabel = '重拍',
  onChangeQuad,
  onResetQuad,
  onCancel,
  onConfirm
}: CaptureQuadScreenProps) {
  return (
    <section className="preview-panel" aria-label="调整识别范围">
      <p className="mobile-capture__hint">
        请框选病历正文区域，排除屏幕边缘、灰色背景和工具栏
      </p>
      <div className="preview-panel__image-wrap">
        {previewUrl ? (
          <img src={previewUrl} alt="待上传病历页面预览" />
        ) : (
          <div className="preview-panel__placeholder" role="img" aria-label="暂无缩略图">
            缩略图
          </div>
        )}
        <QuadSelector width={width} height={height} points={quad} onChange={onChangeQuad} />
      </div>
      <div className="capture-actions capture-actions--split">
        <button className="mobile-button ghost" type="button" onClick={onCancel}>
          {cancelLabel}
        </button>
        <button className="mobile-button secondary" type="button" onClick={onResetQuad}>
          重置框选
        </button>
        <button className="mobile-button" type="button" disabled={isUploading} onClick={onConfirm}>
          {isUploading ? '上传中' : confirmLabel}
        </button>
      </div>
    </section>
  );
}
