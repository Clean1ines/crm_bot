import React, { useState, useEffect, useRef } from 'react';

interface EditWorkflowModalProps {
  isOpen: boolean;
  onClose: () => void;
  initialName: string;
  initialDescription: string;
  onSave: (name: string, description: string) => Promise<void>;
  isSaving?: boolean;
}

export const EditWorkflowModal: React.FC<EditWorkflowModalProps> = ({
  isOpen,
  onClose,
  initialName,
  initialDescription,
  onSave,
  isSaving = false,
}) => {
  const [name, setName] = useState(initialName);
  const [description, setDescription] = useState(initialDescription);
  const [error, setError] = useState('');
  const prevIsOpenRef = useRef(isOpen);

  useEffect(() => {
    // Сбрасываем поля только при открытии модалки (переход false -> true)
    if (isOpen && !prevIsOpenRef.current) {
    // eslint-disable-next-line react-hooks/set-state-in-effect
      setName(initialName);
    // eslint-disable-next-line react-hooks/set-state-in-effect
      setDescription(initialDescription);
    // eslint-disable-next-line react-hooks/set-state-in-effect
      setError('');
    }
    prevIsOpenRef.current = isOpen;
  }, [isOpen, initialName, initialDescription]);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!name.trim()) {
      setError('Name is required');
      return;
    }
    // eslint-disable-next-line react-hooks/set-state-in-effect
    setError('');
    try {
      await onSave(name.trim(), description);
      onClose();
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to update');
    }
  };

  if (!isOpen) return null;

  return (
    <div className="fixed inset-0 bg-black bg-opacity-70 flex items-center justify-center z-50 p-4 backdrop-blur-[2px]">
      <div className="w-full max-w-md bg-[var(--ios-glass-dark)] backdrop-blur-[var(--blur-std)] border border-[var(--ios-border)] rounded-2xl shadow-[var(--shadow-heavy)] p-6">
        <h2 className="text-xl font-bold text-[var(--bronze-base)] mb-4">Edit Workflow</h2>
        <form onSubmit={handleSubmit} className="space-y-4">
          <div>
            <label className="block text-xs text-[var(--text-muted)] uppercase tracking-wider mb-1">
              Workflow Name *
            </label>
            <input
              type="text"
              value={name}
              onChange={(e) => setName(e.target.value)}
              className="w-full bg-[var(--ios-glass-dark)] border border-[var(--ios-border)] rounded px-3 py-2 text-sm text-[var(--text-main)] outline-none focus:border-[var(--bronze-base)]"
              disabled={isSaving}
              autoFocus
            />
          </div>
          <div>
            <label className="block text-xs text-[var(--text-muted)] uppercase tracking-wider mb-1">
              Description
            </label>
            <textarea
              value={description}
              onChange={(e) => setDescription(e.target.value)}
              rows={3}
              className="w-full bg-[var(--ios-glass-dark)] border border-[var(--ios-border)] rounded px-3 py-2 text-sm text-[var(--text-main)] outline-none focus:border-[var(--bronze-base)] resize-none"
              disabled={isSaving}
            />
          </div>
          {error && <p className="text-[var(--accent-danger)] text-xs">{error}</p>}
          <div className="flex justify-end gap-2 pt-2">
            <button
              type="button"
              onClick={onClose}
              className="px-3 py-1.5 text-xs font-semibold rounded bg-[var(--ios-glass-dark)] border border-[var(--ios-border)] text-[var(--text-main)] hover:bg-[var(--ios-glass-bright)] transition-colors"
            >
              Cancel
            </button>
            <button
              type="submit"
              disabled={isSaving}
              className="px-3 py-1.5 text-xs font-semibold rounded bg-[var(--bronze-base)] text-black hover:bg-[var(--bronze-bright)] transition-colors disabled:opacity-30"
            >
              {isSaving ? 'Saving...' : 'Save'}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
};