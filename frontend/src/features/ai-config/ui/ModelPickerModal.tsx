import React from 'react';
import { BaseModal } from '@shared/ui/modal/BaseModal';

interface ModelPickerModalProps {
  isOpen: boolean;
  onClose: () => void;
  models: Array<{ id: string }>;
  onSelect: (modelId: string) => void;
  isPending?: boolean;
}

export const ModelPickerModal: React.FC<ModelPickerModalProps> = ({
  isOpen,
  onClose,
  models,
  onSelect,
  isPending = false,
}) => {
  return (
    <BaseModal isOpen={isOpen} onClose={onClose} title="Select Model">
      <div className="space-y-2 max-h-96 overflow-y-auto">
        {models.length === 0 ? (
          <div className="text-center text-gray-500 py-4">No models available</div>
        ) : (
          models.map((model) => (
            <button
              key={model.id}
              onClick={() => onSelect(model.id)}
              disabled={isPending}
              className="w-full text-left p-3 rounded bg-[var(--ios-glass-dark)] hover:bg-[var(--ios-glass-bright)] transition-colors disabled:opacity-30"
            >
              <div className="font-medium">{model.id}</div>
            </button>
          ))
        )}
      </div>
    </BaseModal>
  );
};