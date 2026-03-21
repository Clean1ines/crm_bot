import React from 'react';
import { BaseModal } from './BaseModal';

interface DeleteConfirmModalProps {
  isOpen: boolean;
  onClose: () => void;
  onConfirm: () => Promise<void>;
  itemName: string;
  itemType: string; // например, "project", "workflow"
  isPending?: boolean;
}

/**
 * Универсальная модалка подтверждения удаления.
 * Показывает сообщение с именем удаляемого объекта и кнопку Delete.
 * Кнопка Cancel наследуется от BaseModal.
 */
export const DeleteConfirmModal: React.FC<DeleteConfirmModalProps> = ({
  isOpen,
  onClose,
  onConfirm,
  itemName,
  itemType,
  isPending = false,
}) => {
  const handleConfirm = async () => {
    await onConfirm();
    // модалка закроется автоматически через onClose, который вызовет родитель после успеха
  };

  return (
    <BaseModal isOpen={isOpen} onClose={onClose} title={`Delete ${itemType}`}>
      <p className="text-[var(--text-main)] mb-4">
        Are you sure you want to delete {itemType}{' '}
        <span className="font-semibold text-[var(--bronze-base)]">"{itemName}"</span>? This action cannot be undone.
      </p>
      <div className="flex justify-end gap-2">
        <button
          onClick={handleConfirm}
          disabled={isPending}
          className="px-3 py-1.5 text-xs font-semibold rounded bg-[var(--accent-danger)] text-white hover:bg-[#ff6961] transition-colors disabled:opacity-30"
        >
          {isPending ? 'Deleting...' : 'Delete'}
        </button>
      </div>
    </BaseModal>
  );
};
