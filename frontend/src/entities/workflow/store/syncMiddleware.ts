import { api } from '@/shared/api';
import { useWorkflowStore } from './workflowStore';
import { getErrorMessage } from '@/shared/api/client';

// MODIFIED: added requiresDialogue to AddNodeData
interface AddNodeData {
  id: string;
  promptKey: string;
  config: Record<string, unknown>;
  position: { x: number; y: number };
  requiresDialogue?: boolean; // ADDED for feature X
}

interface MoveNodeData {
  nodeId: string | undefined;
  position: { x: number; y: number };
}

interface UpdateNodeData {
  nodeId: string | undefined;
  config: { promptKey: string; config: Record<string, unknown> };
}

interface RemoveNodeData {
  nodeId: string | undefined;
}

interface AddEdgeData {
  source: string;
  target: string;
}

interface RemoveEdgeData {
  edgeId: string;
}

type ActionDataMap = {
  addNode: AddNodeData;
  moveNode: MoveNodeData;
  updateNode: UpdateNodeData;
  removeNode: RemoveNodeData;
  addEdge: AddEdgeData;
  removeEdge: RemoveEdgeData;
};

export async function syncWithServer<T extends keyof ActionDataMap>(
  action: T,
  data: ActionDataMap[T]
): Promise<T extends 'addNode' ? string | undefined : void> {
  const state = useWorkflowStore.getState();
  const workflowId = state.ui.currentWorkflowId;
  
  if (!workflowId) {
    console.warn('syncWithServer: No current workflow ID – skipping sync');
    return;
  }

  try {
    switch (action) {
      case 'addNode': {
        const d = data as AddNodeData;
        console.log('[syncWithServer] addNode raw data:', d);
        if (!d.promptKey) {
          console.error('[syncWithServer] promptKey missing in data', d);
          throw new Error('promptKey is required');
        }
        if (!d.position || typeof d.position.x !== 'number' || typeof d.position.y !== 'number') {
          console.error('[syncWithServer] position missing or invalid', d.position);
          throw new Error('position with x and y is required');
        }
        const payload: any = {
          node_id: d.id,
          prompt_key: d.promptKey,
          config: d.config || {},
          position_x: d.position.x,
          position_y: d.position.y,
        };
        // ADDED for feature X: include requires_dialogue if provided
        if (d.requiresDialogue !== undefined) {
          payload.requires_dialogue = d.requiresDialogue;
        }
        console.log('[syncWithServer] addNode payload:', payload);
        const response = await api.workflows.nodes.create(workflowId, payload);
        if (response.error) {
          const errorMessage = getErrorMessage(response.error);
          console.error('[syncWithServer] addNode error details:', response.error);
          throw new Error(errorMessage);
        }
        const recordId = (response.data as { id?: string })?.id;
        return recordId as T extends 'addNode' ? string | undefined : void;
      }
      case 'moveNode': {
        const d = data as MoveNodeData;
        if (!d.nodeId) {
          console.warn('[syncWithServer] moveNode: nodeId is undefined, skipping');
          return;
        }
        const response = await api.workflows.nodes.update(d.nodeId, {
          position_x: d.position.x,
          position_y: d.position.y,
        });
        if (response.error) {
          const errorMessage = getErrorMessage(response.error);
          console.error('[syncWithServer] moveNode error details:', response.error);
          throw new Error(errorMessage);
        }
        return;
      }
      case 'updateNode': {
        const d = data as UpdateNodeData;
        if (!d.nodeId) {
          console.warn('[syncWithServer] updateNode: nodeId is undefined, skipping');
          return;
        }
        const response = await api.workflows.nodes.update(d.nodeId, {
          prompt_key: d.config.promptKey,
          config: d.config.config,
        });
        if (response.error) {
          const errorMessage = getErrorMessage(response.error);
          console.error('[syncWithServer] updateNode error details:', response.error);
          throw new Error(errorMessage);
        }
        return;
      }
      case 'removeNode': {
        const d = data as RemoveNodeData;
        if (!d.nodeId) {
          console.warn('[syncWithServer] removeNode: nodeId is undefined, skipping');
          return;
        }
        const response = await api.workflows.nodes.delete(d.nodeId);
        if (response.error) {
          const errorMessage = getErrorMessage(response.error);
          console.error('[syncWithServer] removeNode error details:', response.error);
          throw new Error(errorMessage);
        }
        return;
      }
      case 'addEdge': {
        const d = data as AddEdgeData;
        const response = await api.workflows.edges.create(workflowId, {
          source_node: d.source,
          target_node: d.target,
          source_output: 'output',
          target_input: 'input',
        });
        if (response.error) {
          const errorMessage = getErrorMessage(response.error);
          console.error('[syncWithServer] addEdge error details:', response.error);
          throw new Error(errorMessage);
        }
        return;
      }
      case 'removeEdge': {
        const d = data as RemoveEdgeData;
        const response = await api.workflows.edges.delete(d.edgeId);
        if (response.error) {
          const errorMessage = getErrorMessage(response.error);
          console.error('[syncWithServer] removeEdge error details:', response.error);
          throw new Error(errorMessage);
        }
        return;
      }
      default:
        console.warn(`Unknown action: ${action}`);
    }
  } catch (error) {
    console.error('syncWithServer error:', error);
    throw error;
  }
}