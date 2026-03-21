import React from 'react';
import { useNavigate, useSearchParams } from 'react-router-dom';
import { ChatInterface } from '@/widgets/chat-window/ui/ChatInterface';
import { api } from '@shared/api';
import type { ValidateExecutionResponse } from '@shared/api';
import { useNotification } from '@/shared/lib/notification/useNotifications';

export const WorkflowChatPage: React.FC = () => {
  const [searchParams] = useSearchParams();
  const runId = searchParams.get('runId');
  const executionId = searchParams.get('executionId');
  const navigate = useNavigate();
  const { showNotification } = useNotification();

  if (!runId || !executionId) {
    return <div className="p-4">Missing run or execution ID</div>;
  }

  const handleValidate = async () => {
    try {
      const { data, error } = await api.executions.validate(executionId);
      if (error) throw error;
      const response = data as ValidateExecutionResponse;
      if (response.next_execution_id) {
        navigate(`/workspace/chat?runId=${runId}&executionId=${response.next_execution_id}`);
      } else {
        showNotification('Workflow completed!', 'success');
        navigate('/workspace');
      }
    } catch {
      showNotification('Validation failed', 'error');
    }
  };

  return (
    <div className="h-full flex flex-col relative">
      <div className="flex-1">
        <ChatInterface executionId={executionId} />
      </div>
      <div className="absolute bottom-24 right-4 z-10">
        <button
          onClick={handleValidate}
          className="px-4 py-2 bg-emerald-600 text-white rounded shadow-lg hover:bg-emerald-500 transition-colors"
        >
          Validate
        </button>
      </div>
    </div>
  );
};