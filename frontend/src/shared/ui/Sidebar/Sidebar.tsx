import React from 'react';

interface SidebarProps {
  /** Открыта ли боковая панель */
  isOpen: boolean;
  /** Функция закрытия (вызывается при клике на крестик) */
  onClose: () => void;
  /** Заголовок (опционально) */
  header?: React.ReactNode;
  /** Нижняя часть (футер) */
  footer?: React.ReactNode;
  /** Основное содержимое */
  children: React.ReactNode;
  /** Позиция: слева или справа (по умолчанию left) */
  position?: 'left' | 'right';
  /** Ширина (Tailwind класс, по умолчанию 'w-64') */
  width?: string;
  /** Дополнительные CSS классы */
  className?: string;
}

/**
 * Базовая боковая панель с возможностью закрытия.
 * Поддерживает левое/правое расположение и кастомизацию ширины.
 */
export const Sidebar = React.forwardRef<HTMLElement, SidebarProps>(
  (
    {
      isOpen,
      onClose,
      header,
      footer,
      children,
      position = 'left',
      width = 'w-64',
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
          fixed top-0 h-full z-50
          bg-[var(--ios-glass)] backdrop-blur-md
          border-[var(--ios-border)]
          ${positionClasses}
          ${width}
          flex flex-col
          ${className}
        `}
        data-testid="sidebar"
      >
        {/* Кнопка закрытия */}
        <div className="flex justify-end p-2">
          <button
            onClick={onClose}
            className="p-1 text-[var(--text-muted)] hover:text-[var(--text-main)] transition-colors"
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
        {header && <div className="px-4 pb-2 border-b border-[var(--ios-border)]">{header}</div>}

        {/* Основное содержимое (прокручиваемое) */}
        <div className="flex-1 overflow-y-auto p-2">{children}</div>

        {/* Футер (если есть) */}
        {footer && <div className="p-4 border-t border-[var(--ios-border)]">{footer}</div>}
      </aside>
    );
  }
);

Sidebar.displayName = 'Sidebar';
