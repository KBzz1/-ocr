import type { ReactNode } from 'react';

type IconButtonProps = {
  label: string;
  children: ReactNode;
  onClick?: () => void;
  variant?: 'plain' | 'soft' | 'primary';
};

export function IconButton({ label, children, onClick, variant = 'plain' }: IconButtonProps) {
  return (
    <button
      className={`icon-button icon-button--${variant}`}
      type="button"
      aria-label={label}
      title={label}
      onClick={onClick}
    >
      {children}
    </button>
  );
}
