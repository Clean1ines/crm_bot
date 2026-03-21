import React, { useState, useEffect, useRef } from 'react';
import { BaseModal } from '@shared/ui';

interface EditNodeModalProps {
  isOpen: boolean;
  onClose: () => void;
  initialPromptKey: string;
  initialConfig: Record<string, unknown>;
  onSave: (promptKey: string, config: Record<string, unknown>) => Promise<void>;
  isSaving?: boolean;
}

export const EditNodeModal: React.FC<EditNodeModalProps> = ({
  isOpen,
  onClose,
  initialPromptKey,
  initialConfig,
  onSave,
  isSaving = false,
}) => {
  const [promptKey, setPromptKey] = useState(initialPromptKey);
  const [customPrompt, setCustomPrompt] = useState(
    typeof initialConfig.system_prompt === 'string' ? initialConfig.system_prompt : ''
  );
  const [error, setError] = useState('');
  const prevIsOpenRef = useRef(isOpen);

  useEffect(() => {
    if (isOpen && !prevIsOpenRef.current) {
      // eslint-disable-next-line react-hooks/set-state-in-effect
      setPromptKey(initialPromptKey);
      // eslint-disable-next-line react-hooks/set-state-in-effect
      setCustomPrompt(
        typeof initialConfig.system_prompt === 'string' ? initialConfig.system_prompt : ''
      );
      // eslint-disable-next-line react-hooks/set-state-in-effect
      setError('');
    }
    prevIsOpenRef.current = isOpen;
  }, [isOpen, initialPromptKey, initialConfig]);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!promptKey.trim()) {
      setError('Prompt key is required');
      return;
    }
    setError('');
    const newConfig = { system_prompt: customPrompt };
    await onSave(promptKey.trim(), newConfig);
    onClose();
  };

  return (
    <BaseModal isOpen={isOpen} onClose={onClose} title="Edit Node">
      <form onSubmit={handleSubmit} className="space-y-4">
        {error && <p className="text-xs text-[var(--accent-danger)]">{error}</p>}
        <div>
          <label className="block text-xs text-[var(--text-muted)] uppercase tracking-wider mb-1">
            Prompt Key *
          </label>
          <input
            type="text"
            value={promptKey}
            onChange={(e) => setPromptKey(e.target.value)}
            className="w-full bg-[var(--ios-glass-dark)] border border-[var(--ios-border)] rounded px-3 py-2 text-sm text-[var(--text-main)] outline-none focus:border-[var(--bronze-base)]"
            disabled={isSaving}
            autoFocus
          />
        </div>
        <div>
          <label className="block text-xs text-[var(--text-muted)] uppercase tracking-wider mb-1">
            Prompt Text
          </label>
          <textarea
            value={customPrompt}
            onChange={(e) => setCustomPrompt(e.target.value)}
            rows={5}
            className="w-full bg-[var(--ios-glass-dark)] border border-[var(--ios-border)] rounded px-3 py-2 text-sm text-[var(--text-main)] outline-none focus:border-[var(--bronze-base)] resize-vertical"
            disabled={isSaving}
          />
        </div>
        <div className="flex justify-end gap-2 pt-2">
          <button
            type="submit"
            disabled={isSaving}
            className="px-3 py-1.5 text-xs font-semibold rounded bg-[var(--bronze-base)] text-black hover:bg-[var(--bronze-bright)] transition-colors disabled:opacity-30"
          >
            {isSaving ? 'Saving...' : 'Save'}
          </button>
        </div>
      </form>
    </BaseModal>
  );
};