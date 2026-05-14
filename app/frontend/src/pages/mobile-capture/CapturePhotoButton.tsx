import { useRef } from 'react';

interface CapturePhotoButtonProps {
  disabled: boolean;
  label?: string;
  onFileSelected: (file: File) => void;
  onClick?: () => void;
}

export function CapturePhotoButton({
  disabled,
  label = '拍摄/选择图片',
  onFileSelected,
  onClick
}: CapturePhotoButtonProps) {
  const inputRef = useRef<HTMLInputElement>(null);

  return (
    <>
      <input
        ref={inputRef}
        className="visually-hidden-input"
        aria-label={label}
        type="file"
        accept="image/jpeg,image/png,image/bmp"
        capture="environment"
        disabled={disabled}
        onChange={(event) => {
          const file = event.currentTarget.files?.[0];
          if (file) onFileSelected(file);
          event.currentTarget.value = '';
        }}
      />
      <button
        className="mobile-button capture-photo-btn"
        type="button"
        disabled={disabled}
        onClick={() => {
          onClick?.();
          inputRef.current?.click();
        }}
      >
        拍摄/选择图片
      </button>
    </>
  );
}
