import React from 'react';
import { BaseModal } from '@shared/ui/modal/BaseModal';

interface Node {
  id: string;
  recordId?: string;
  promptKey: string;
  config?: Record<string, unknown>;
}

interface NodePickerModalProps {
  isOpen: boolean;
  onClose: () => void;
  nodes: Node[];
  onSelect: (node: Node) => void;
}

export const NodePickerModal: React.FC<NodePickerModalProps> = ({
  isOpen,
  onClose,
  nodes,
  onSelect,
}) => {
  return (
    <BaseModal isOpen={isOpen} onClose={onClose} title="Select Start Node">
      <div className="space-y-2 max-h-96 overflow-y-auto">
        {nodes.length === 0 ? (
          <div className="text-center text-gray-500 py-4">No nodes in this workflow</div>
        ) : (
          nodes.map((node) => (
            <button
              key={node.id}
              onClick={() => onSelect(node)}
              className="w-full text-left p-3 rounded bg-[var(--ios-glass-dark)] hover:bg-[var(--ios-glass-bright)] transition-colors"
            >
              <div className="font-medium">{node.promptKey}</div>
              {(node.config as { description?: string })?.description && (
                <div className="text-xs text-gray-500 mt-1">
                  {(node.config as { description?: string }).description}
                </div>
              )}
              {!node.recordId && (
                <div className="text-xs text-yellow-500 mt-1">⏳ Syncing...</div>
              )}
            </button>
          ))
        )}
      </div>
    </BaseModal>
  );
};