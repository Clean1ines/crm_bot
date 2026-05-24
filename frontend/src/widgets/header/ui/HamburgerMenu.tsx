import React from 'react';
import { useNavigate } from 'react-router-dom';
import { t } from '@shared/i18n';

interface HamburgerMenuProps {
  /** Callback to open the sidebar */
  onOpenSidebar: () => void;
  /** Whether to show the home icon (for workspace page) */
  showHomeIcon?: boolean;
}

/**
 * Floating hamburger menu button, optionally with a home icon.
 * Used when the sidebar is collapsed.
 */
export const HamburgerMenu: React.FC<HamburgerMenuProps> = ({ onOpenSidebar, showHomeIcon = false }) => {
  const navigate = useNavigate();

  return (
    <div className="fixed top-4 left-4 z-50 flex gap-2">
      <button
        onClick={onOpenSidebar}
        className="rounded-lg border border-[var(--border-primary)] bg-[var(--control-bg)] p-2 text-[var(--text-muted)] backdrop-blur-sm transition-colors hover:bg-[var(--control-bg-hover)] hover:text-[var(--text-primary)]"
        aria-label={t('sidebar.actions.open')}
      >
        <svg className="w-5 h-5" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
          <line x1="3" y1="12" x2="21" y2="12" />
          <line x1="3" y1="6" x2="21" y2="6" />
          <line x1="3" y1="18" x2="21" y2="18" />
        </svg>
      </button>
      {showHomeIcon && (
        <button
          onClick={() => navigate('/')}
          className="rounded-lg border border-[var(--border-primary)] bg-[var(--control-bg)] p-2 text-[var(--text-muted)] backdrop-blur-sm transition-colors hover:bg-[var(--control-bg-hover)] hover:text-[var(--text-primary)]"
          aria-label={t('sidebar.actions.goToProjects')}
        >
          <svg className="w-5 h-5" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
            <path d="M3 9.5L12 4L21 9.5V20H3V9.5Z" />
            <path d="M8 12h8M8 16h6" />
          </svg>
        </button>
      )}
    </div>
  );
};
