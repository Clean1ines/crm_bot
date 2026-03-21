// frontend/src/entities/workflow/store/types.ts
export interface GraphNode {
  id: string;
  recordId?: string;
  type: string;
  promptKey: string;
  config: Record<string, unknown>;
  requiresDialogue?: boolean; // ADDED for feature X
}

export interface GraphEdge {
  id: string;
  source: string;
  target: string;
}

export interface Layout {
  positions: Record<string, { x: number; y: number }>;
  sizes: Record<string, { width: number; height: number }>; // теперь используем для хранения ширины лейбла
}

export interface UIState {
  selectedNodeId: string | null;
  sidebarOpen: boolean;
  workflows: { id: string; name: string; description?: string }[];
  currentWorkflowId: string | null;
}

export interface ApiNode {
  id: string;
  node_id: string;
  prompt_key: string;
  config: Record<string, unknown>;
  position_x: number;
  position_y: number;
  type?: string;
  created_at?: string;
  updated_at?: string;
  requires_dialogue?: boolean; // ADDED for feature X
}

export interface ApiEdge {
  id: string;
  source_node: string;
  target_node: string;
  source_output?: string;
  target_input?: string;
  created_at?: string;
}

export interface ApiWorkflowDetail {
  workflow: Record<string, unknown>;
  nodes: ApiNode[];
  edges: ApiEdge[];
}

export interface WorkflowStore {
  graph: {
    nodes: GraphNode[];
    edges: GraphEdge[];
  };
  layout: Layout;
  ui: UIState;
  containerWidth: number;
  containerHeight: number;

  setContainerSize: (width: number, height: number) => void;
  clampAllPositions: () => void;

  loadWorkflow: (data: ApiWorkflowDetail) => void;
  addNode: (nodeData: Omit<GraphNode, 'id' | 'recordId'>, position?: { x: number; y: number }) => void;
  moveNode: (nodeId: string, position: { x: number; y: number }) => void;
  updateNodeConfig: (nodeId: string, config: Partial<GraphNode>) => void;
  removeNode: (nodeId: string) => void;
  addEdge: (source: string, target: string) => void;
  removeEdge: (edgeId: string) => void;
  selectNode: (nodeId: string | null) => void;
  toggleSidebar: () => void;
  setWorkflows: (workflows: UIState['workflows']) => void;
  selectWorkflow: (workflowId: string | null) => void;
  setNodePositionOptimistic: (nodeId: string, position: { x: number; y: number }) => void;
  updateNodeSize: (nodeId: string, size: { width: number; height: number }) => void;
}