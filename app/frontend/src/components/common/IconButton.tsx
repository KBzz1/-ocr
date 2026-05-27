import type { ReactNode } from 'react';

type IconButtonProps = {
  label: string;
  children: ReactNode;
  onClick?: () => void;
  variant?: 'plain' | 'soft' | 'primary';
  disabled?: boolean;
};

export function IconButton({ label, children, onClick, variant = 'plain', disabled }: IconButtonProps) {
  return (
    <button
      className={`icon-button icon-button--${variant}`}
      type="button"
      aria-label={label}
      title={label}
      onClick={onClick}
      disabled={disabled}
    >
      {children}
    </button>
  );
}
