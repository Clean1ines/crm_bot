// frontend/src/entities/workflow/store/workflowStore.ts
import { create } from 'zustand';
import { subscribeWithSelector } from 'zustand/middleware';
import { WorkflowStore, GraphNode, ApiWorkflowDetail, ApiNode, ApiEdge } from './types';
import { deterministicNodeId, deterministicEdgeId } from '@/shared/lib/deterministicId';
import { syncWithServer } from './syncMiddleware';
import toast from 'react-hot-toast';

export const useWorkflowStore = create<WorkflowStore>()(
  subscribeWithSelector((set, get) => ({
    graph: {
      nodes: [],
      edges: [],
    },
    layout: {
      positions: {},
      sizes: {},
    },
    ui: {
      selectedNodeId: null,
      sidebarOpen: true,
      workflows: [],
      currentWorkflowId: null,
    },
    containerWidth: 0,
    containerHeight: 0,

    setContainerSize: (width: number, height: number) => {
      set({ containerWidth: width, containerHeight: height });
      get().clampAllPositions();
    },

    clampAllPositions: () => {
      const { containerWidth, containerHeight, layout } = get();
      if (containerWidth === 0 || containerHeight === 0) return;

      const newPositions = { ...layout.positions };
      let changed = false;

      Object.entries(newPositions).forEach(([id, pos]) => {
        const size = layout.sizes[id];
        const maxX = containerWidth - (size?.width ?? 0);
        const maxY = containerHeight - (size?.height ?? 0);
        const clampedX = Math.max(0, Math.min(pos.x, maxX));
        const clampedY = Math.max(0, Math.min(pos.y, maxY));
        if (clampedX !== pos.x || clampedY !== pos.y) {
          newPositions[id] = { x: clampedX, y: clampedY };
          changed = true;
        }
      });

      if (changed) {
        set({ layout: { ...layout, positions: newPositions } });
      }
    },

    loadWorkflow: (data: ApiWorkflowDetail) => {
      console.log('[loadWorkflow] loading workflow with data:', data);
      const nodes: GraphNode[] = data.nodes.map((n: ApiNode) => {
        const id = deterministicNodeId(n.type || 'prompt', n.prompt_key, n.config);
        return {
          id,
          recordId: n.id,
          type: n.type || 'prompt',
          promptKey: n.prompt_key,
          config: n.config,
          requiresDialogue: n.requires_dialogue, // ADDED for feature X
        };
      });
      const positions: Record<string, { x: number; y: number }> = {};
      data.nodes.forEach((n: ApiNode) => {
        const id = deterministicNodeId(n.type || 'prompt', n.prompt_key, n.config);
        positions[id] = { x: n.position_x, y: n.position_y };
      });
      const edges = data.edges.map((e: ApiEdge) => ({
        id: e.id,
        source: e.source_node,
        target: e.target_node,
      }));
      console.log('[loadWorkflow] setting nodes:', nodes.length, 'edges:', edges.length);
      console.log('[loadWorkflow] positions:', Object.keys(positions).length);
      set({
        graph: { nodes, edges },
        layout: { ...get().layout, positions },
      });
      get().clampAllPositions();
    },

    addNode: (nodeData: Omit<GraphNode, 'id' | 'recordId'>, position = { x: 100, y: 100 }) => {
      const id = deterministicNodeId(nodeData.type, nodeData.promptKey, nodeData.config);
      console.log('[addNode] creating node with id:', id);
      console.log('[addNode] nodeData:', nodeData);
      console.log('[addNode] position:', position);
      
      set((state) => ({
        graph: {
          ...state.graph,
          nodes: [...state.graph.nodes, { ...nodeData, id, recordId: undefined }],
        },
        layout: {
          ...state.layout,
          positions: { ...state.layout.positions, [id]: position },
        },
      }));

      syncWithServer('addNode', { ...nodeData, id, position })
        .then((recordId) => {
          console.log('[workflowStore] addNode success, recordId:', recordId);
          if (recordId) {
            set((state) => ({
              graph: {
                ...state.graph,
                nodes: state.graph.nodes.map((n) =>
                  n.id === id ? { ...n, recordId } : n
                ),
              },
            }));
          }
        })
        .catch((error) => {
          console.error('[workflowStore] addNode error:', error);
          set((state) => ({
            graph: {
              ...state.graph,
              nodes: state.graph.nodes.filter((n) => n.id !== id),
            },
            layout: {
              ...state.layout,
              positions: Object.fromEntries(
                Object.entries(state.layout.positions).filter(([k]) => k !== id)
              ),
            },
          }));
          toast.error('Failed to create node');
        });
    },

    setNodePositionOptimistic: (nodeId: string, position: { x: number; y: number }) => 
      set((state) => ({
        layout: {
          ...state.layout,
          positions: { ...state.layout.positions, [nodeId]: position },
        },
      })),

    moveNode: (nodeId, position) => {
      const node = get().graph.nodes.find(n => n.id === nodeId);
      if (!node) return;

      const { containerWidth, containerHeight, layout } = get();
      const size = layout.sizes[nodeId];
      const maxX = containerWidth - (size?.width ?? 0);
      const maxY = containerHeight - (size?.height ?? 0);
      const clampedX = Math.max(0, Math.min(position.x, maxX));
      const clampedY = Math.max(0, Math.min(position.y, maxY));

      set((state) => ({
        layout: {
          ...state.layout,
          positions: { ...state.layout.positions, [nodeId]: { x: clampedX, y: clampedY } },
        },
      }));

      syncWithServer('moveNode', { nodeId: node.recordId, position: { x: clampedX, y: clampedY } }).catch((error) => {
        console.error('[moveNode] error:', error);
        toast.error('Failed to save node position');
      });
    },

    updateNodeConfig: (nodeId, config) => {
      const node = get().graph.nodes.find(n => n.id === nodeId);
      if (!node) return;

      set((state) => ({
        graph: {
          ...state.graph,
          nodes: state.graph.nodes.map((n) =>
            n.id === nodeId ? { ...n, ...config } : n
          ),
        },
      }));

      syncWithServer('updateNode', {
        nodeId: node.recordId,
        config: {
          promptKey: config.promptKey || '',
          config: config.config || {},
        },
      }).catch((error) => {
        console.error('[updateNode] error:', error);
        toast.error('Failed to update node');
      });
    },

    removeNode: (nodeId) => {
      const node = get().graph.nodes.find(n => n.id === nodeId);
      if (!node) return;

      set((state) => {
        const newEdges = state.graph.edges.filter(
          (e) => e.source !== node.id && e.target !== node.id
        );
        const newPositions = { ...state.layout.positions };
        delete newPositions[nodeId];
        const newSizes = { ...state.layout.sizes };
        delete newSizes[nodeId];
        return {
          graph: {
            nodes: state.graph.nodes.filter((n) => n.id !== nodeId),
            edges: newEdges,
          },
          layout: { ...state.layout, positions: newPositions, sizes: newSizes },
        };
      });

      syncWithServer('removeNode', { nodeId: node.recordId }).catch((error) => {
        console.error('[removeNode] error:', error);
        toast.error('Failed to delete node');
      });
    },

    addEdge: (sourceId, targetId) => {
      console.log('[workflowStore] addEdge', sourceId, targetId);
      const nodes = get().graph.nodes;
      const sourceNode = nodes.find(n => n.id === sourceId);
      const targetNode = nodes.find(n => n.id === targetId);
      if (!sourceNode || !targetNode) {
        toast.error('Node not found');
        return;
      }
      if (!sourceNode.recordId || !targetNode.recordId) {
        toast.error('Please wait for nodes to be saved before connecting');
        return;
      }
      const id = deterministicEdgeId(sourceId, targetId);
      set((state) => {
        const exists = state.graph.edges.some(e => e.source === sourceId && e.target === targetId);
        if (exists) return state;
        return {
          graph: {
            ...state.graph,
            edges: [...state.graph.edges, { id, source: sourceId, target: targetId }],
          },
        };
      });
      syncWithServer('addEdge', { source: sourceId, target: targetId }).catch((error) => {
        console.error('[addEdge] error:', error);
        set((state) => ({
          graph: {
            ...state.graph,
            edges: state.graph.edges.filter(e => e.id !== id),
          },
        }));
        toast.error('Failed to create edge');
      });
    },

    removeEdge: (edgeId) => {
      set((state) => ({
        graph: {
          ...state.graph,
          edges: state.graph.edges.filter((e) => e.id !== edgeId),
        },
      }));
      syncWithServer('removeEdge', { edgeId }).catch((error) => {
        console.error('[removeEdge] error:', error);
        toast.error('Failed to delete edge');
      });
    },

    selectNode: (nodeId) => set((state) => ({ ui: { ...state.ui, selectedNodeId: nodeId } })),
    toggleSidebar: () => set((state) => ({ ui: { ...state.ui, sidebarOpen: !state.ui.sidebarOpen } })),
    setWorkflows: (workflows) => {
      console.log('[setWorkflows] setting workflows:', workflows.length);
      set((state) => ({ ui: { ...state.ui, workflows } }));
    },
    selectWorkflow: (workflowId) => {
      console.log('[selectWorkflow] selecting workflow:', workflowId);
      set((state) => ({ ui: { ...state.ui, currentWorkflowId: workflowId } }));
    },
    updateNodeSize: (nodeId: string, size: { width: number; height: number }) => {
      set((state) => ({
        layout: {
          ...state.layout,
          sizes: { ...state.layout.sizes, [nodeId]: size },
        },
      }));
      // после обновления размера пересчитываем позицию, чтобы узел не вылез за границы
      get().clampAllPositions();
    },
  }))
);