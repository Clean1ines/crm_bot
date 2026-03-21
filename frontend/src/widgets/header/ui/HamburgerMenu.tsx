import React from 'react';
import { useNavigate } from 'react-router-dom';

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
        className="p-2 text-[var(--text-muted)] hover:text-[var(--text-main)] transition-colors bg-[var(--ios-glass-dark)] backdrop-blur-sm rounded-lg border border-[var(--ios-border)]"
        aria-label="Open sidebar"
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
          className="p-2 text-[var(--text-muted)] hover:text-[var(--text-main)] transition-colors bg-[var(--ios-glass-dark)] backdrop-blur-sm rounded-lg border border-[var(--ios-border)]"
          aria-label="Go to projects"
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
