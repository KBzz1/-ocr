import type { ReactNode } from 'react';

import closeIconUrl from '../../assets/icons/actions/icon-close.svg?url';

type IconButtonProps = {
  label: string;
  children: ReactNode;
  onClick?: () => void;
  variant?: 'plain' | 'soft' | 'primary';
  disabled?: boolean;
};

export function IconButton({ label, children, onClick, variant = 'plain', disabled }: IconButtonProps) {
  const isCloseButton = label.includes('关闭');

  return (
    <button
      className={`icon-button icon-button--${variant}${isCloseButton ? ' icon-button--close' : ''}`}
      type="button"
      aria-label={label}
      title={label}
      onClick={onClick}
      disabled={disabled}
    >
      {isCloseButton ? <img src={closeIconUrl} alt="" aria-hidden="true" /> : children}
    </button>
  );
}
