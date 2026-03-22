import React from 'react';
import { ChatCanvas } from '@widgets/chat-panel/ui/ChatCanvas';

interface ChatInterfaceProps {
  projectId: string;
  model?: string;
  onModelChange?: (model: string) => void;
  availableModels?: { id: string; name: string }[];
}

export const ChatInterface: React.FC<ChatInterfaceProps> = ({
  projectId,
  model,
  onModelChange,
  availableModels,
}) => {
  return (
    <div className="h-full w-full flex flex-col">
      <ChatCanvas
        projectId={projectId}
        model={model}
        onModelChange={onModelChange}
        availableModels={availableModels}
      />
    </div>
  );
};