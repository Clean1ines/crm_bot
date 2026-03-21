// frontend/src/components/ios/NodeModal.tsx
// ADDED: Modal for creating custom prompt nodes (SRP extraction)

import React from 'react';

interface NodeModalProps {
  visible: boolean;
  onClose: () => void;
  title: string;
  onTitleChange: (title: string) => void;
  prompt: string;
  onPromptChange: (prompt: string) => void;
  requiresDialogue: boolean;          // ADDED for feature X
  onRequiresDialogueChange: (value: boolean) => void; // ADDED for feature X
  onConfirm: () => void;
  validationError: string | null;
}

export const NodeModal: React.FC<NodeModalProps> = ({
  visible,
  onClose,
  title,
  onTitleChange,
  prompt,
  onPromptChange,
  requiresDialogue,
  onRequiresDialogueChange,
  onConfirm,
  validationError,
}) => {
  if (!visible) return null;

  return (
    <div className="absolute inset-0 z-[2000] flex items-center justify-center bg-black/60 backdrop-blur-sm">
      <div className="bg-[var(--ios-glass)] border border-[var(--ios-border)] rounded-lg p-6 w-[500px] shadow-[var(--shadow-heavy)]">
        <div className="flex items-center justify-between mb-4">
          <h3 className="text-lg font-bold text-[var(--bronze-base)]">Custom Prompt Node</h3>
          <button
            onClick={onClose}
            className="text-[var(--text-muted)] hover:text-[var(--accent-danger)]"
          >
            <svg className="w-5 h-5" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
              <line x1="18" y1="6" x2="6" y2="18" />
              <line x1="6" y1="6" x2="18" y2="18" />
            </svg>
          </button>
        </div>
        <div className="mb-4">
          <label className="text-[9px] text-[var(--text-muted)] uppercase tracking-wider block mb-1">Node Title</label>
          <input
            type="text"
            value={title}
            onChange={(e) => onTitleChange(e.target.value)}
            placeholder="e.g., My Custom Node"
            className="w-full bg-[var(--ios-glass-dark)] border border-[var(--ios-border)] rounded px-3 py-2 text-sm text-[var(--text-main)] outline-none focus:border-[var(--bronze-base)]"
          />
        </div>
        <div className="mb-4">
          <label className="text-[9px] text-[var(--text-muted)] uppercase tracking-wider block mb-1">System Prompt</label>
          <textarea
            value={prompt}
            onChange={(e) => onPromptChange(e.target.value)}
            placeholder="Enter your system prompt..."
            className="w-full h-40 bg-[var(--ios-glass-dark)] border border-[var(--ios-border)] rounded p-3 text-sm text-[var(--text-main)] outline-none focus:border-[var(--bronze-base)] font-mono"
          />
        </div>
        {/* ADDED: Checkbox for requires dialogue */}
        <div className="mb-4 flex items-center gap-2">
          <input
            type="checkbox"
            id="requiresDialogue"
            checked={requiresDialogue}
            onChange={(e) => onRequiresDialogueChange(e.target.checked)}
            className="w-4 h-4"
          />
          <label htmlFor="requiresDialogue" className="text-xs text-[var(--text-main)]">
            Requires dialogue (node will enter chat mode)
          </label>
        </div>
        {validationError && (
          <div className="mb-4 text-[10px] text-[var(--accent-warning)] bg-[var(--accent-warning)]/10 border border-[var(--accent-warning)] rounded px-3 py-2">
            ⚠️ {validationError}
          </div>
        )}
        <div className="flex gap-3">
          <button
            onClick={onConfirm}
            className="flex-1 px-4 py-2 text-xs font-semibold rounded bg-[var(--bronze-base)] text-black hover:bg-[var(--bronze-bright)] transition-colors"
          >
            Add Node
          </button>
          <button
            onClick={onClose}
            className="flex-1 px-4 py-2 text-xs font-semibold rounded border border-[var(--ios-border)] text-[var(--text-muted)] hover:bg-[var(--ios-glass-bright)] transition-colors"
          >
            Cancel
          </button>
        </div>
      </div>
    </div>
  );
};