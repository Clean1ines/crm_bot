import React from 'react';

interface SidebarProps {
  isOpen: boolean;
  onClose: () => void;
  header?: React.ReactNode;
  footer?: React.ReactNode;
  children: React.ReactNode;
  position?: 'left' | 'right';
  width?: string;
  className?: string;
}

export const Sidebar = React.forwardRef<HTMLElement, SidebarProps>(
  (
    {
      isOpen,
      onClose,
      header,
      footer,
      children,
      position = 'left',
      width = 'w-72',
      className = '',
    },
    ref
  ) => {
    if (!isOpen) return null;

    const positionClasses =
      position === 'left'
        ? 'left-0 border-r'
        : 'right-0 border-l';

    return (
      <aside
        ref={ref}
        className={`
          relative h-full z-40 
          bg-[var(--bg-primary)]
          border-[var(--border-subtle)]
          ${positionClasses}
          ${width}
          flex flex-col
          ${className}
        `}
        data-testid="sidebar"
      >
        {/* Кнопка закрытия */}
        <div className="flex justify-end p-3">
          <button
            onClick={onClose}
            className="p-1 text-[var(--text-muted)] hover:text-[var(--text-primary)] transition-colors"
            aria-label="Close sidebar"
            data-testid="close-sidebar"
          >
            <svg className="w-4 h-4" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
              <line x1="18" y1="6" x2="6" y2="18" />
              <line x1="6" y1="6" x2="18" y2="18" />
            </svg>
          </button>
        </div>

        {/* Заголовок (если есть) */}
        {header && <div className="px-4 pb-3 border-b border-[var(--border-subtle)]">{header}</div>}

        {/* Основное содержимое (прокручиваемое) */}
        <div className="flex-1 overflow-y-auto p-2">{children}</div>

        {/* Футер (если есть) */}
        {footer && <div className="p-4 border-t border-[var(--border-subtle)]">{footer}</div>}
      </aside>
    );
  }
);

Sidebar.displayName = 'Sidebar';
