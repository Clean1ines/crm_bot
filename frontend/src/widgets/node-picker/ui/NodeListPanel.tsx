import React, { useState, useEffect } from 'react';
import toast from 'react-hot-toast';
import { EditNodeModal } from '@/features/node/edit-content/ui/EditNodeModal';
import { useWorkflowStore } from '@/entities/workflow/store/workflowStore';
import { GraphNode, ApiWorkflowDetail } from '@/entities/workflow/store/types';
import { api } from '@shared/api';

interface NodeListPanelProps {
  visible: boolean;
  onClose: () => void;
  nodes: GraphNode[];
  onAddNode: (node: Omit<GraphNode, 'id'>, position?: { x: number; y: number }) => void;
  onUpdateNode?: (nodeId: string, promptKey: string, config: Record<string, unknown>) => Promise<void>;
  onDeleteNode?: (nodeId: string) => void;
  currentWorkflowId?: string | null;
}

type TabType = 'created' | 'import';
type ImportStep = 'idle' | 'select-project' | 'select-workflow' | 'select-node';

interface Project {
  id: string;
  name: string;
}

interface WorkflowSummary {
  id: string;
  name: string;
}

interface NodeSummary {
  node_id: string;
  prompt_key: string;
  config?: Record<string, unknown>;
}

const CANVAS_CENTER = { x: 600, y: 400 };

const isDuplicate = (nodes: GraphNode[], promptKey: string, config: Record<string, unknown>): boolean => {
  return nodes.some(node => 
    node.promptKey === promptKey && 
    JSON.stringify(node.config) === JSON.stringify(config)
  );
};

export const NodeListPanel: React.FC<NodeListPanelProps> = ({
  visible,
  onClose,
  nodes,
  onAddNode,
  onUpdateNode,
  onDeleteNode,
  currentWorkflowId,
}) => {
  const [activeTab, setActiveTab] = useState<TabType>('created');
  const [importStep, setImportStep] = useState<ImportStep>('idle');
  const [projects, setProjects] = useState<Project[]>([]);
  const [workflows, setWorkflows] = useState<WorkflowSummary[]>([]);
  const [availableNodes, setAvailableNodes] = useState<NodeSummary[]>([]);
  const [loading, setLoading] = useState(false);
  const [previewNode, setPreviewNode] = useState<NodeSummary | null>(null);
  const [editingNode, setEditingNode] = useState<GraphNode | null>(null);

  const store = useWorkflowStore();

  useEffect(() => {
    if (!visible) {
      setActiveTab('created');
      setImportStep('idle');
      setProjects([]);
      setWorkflows([]);
      setAvailableNodes([]);
      setPreviewNode(null);
      setEditingNode(null);
    }
  }, [visible]);

  const handleImportClick = () => {
    setActiveTab('import');
    setImportStep('select-project');
    loadProjects();
  };

  const loadProjects = async () => {
    setLoading(true);
    try {
      const { data, error } = await api.projects.list();
      if (error) throw error;
      setProjects(Array.isArray(data) ? data : []);
    } catch (err) {
      toast.error('Ошибка загрузки проектов');
      console.error(err);
      setImportStep('idle');
    } finally {
      setLoading(false);
    }
  };

  const loadWorkflows = async (projectId: string) => {
    setLoading(true);
    try {
      const { data, error } = await api.workflows.list(projectId);
      if (error) throw error;
      const workflowsData = Array.isArray(data) ? data : [];
      const filtered = currentWorkflowId
        ? workflowsData.filter((wf: WorkflowSummary) => wf.id !== currentWorkflowId)
        : workflowsData;
      setWorkflows(filtered);
    } catch (err) {
      toast.error('Ошибка загрузки воркфлоу');
      console.error(err);
      setImportStep('select-project');
    } finally {
      setLoading(false);
    }
  };

  const loadNodes = async (workflowId: string) => {
    setLoading(true);
    try {
      const { data, error } = await api.workflows.get(workflowId);
      if (error) throw error;
      const detail = data as ApiWorkflowDetail;
      setAvailableNodes(detail.nodes || []);
    } catch (err) {
      toast.error('Ошибка загрузки узлов');
      console.error(err);
      setImportStep('select-workflow');
    } finally {
      setLoading(false);
    }
  };

  const handleProjectSelect = (projectId: string) => {
    setImportStep('select-workflow');
    loadWorkflows(projectId);
  };

  const handleWorkflowSelect = (workflowId: string) => {
    setImportStep('select-node');
    loadNodes(workflowId);
  };

  const handleNodeSelect = (node: NodeSummary) => {
    setPreviewNode({
      ...node,
      prompt_key: node.prompt_key || '',
    });
  };

  const handlePreviewSave = async (promptKey: string, config: Record<string, unknown>) => {
    if (!previewNode) return;

    if (!promptKey.trim()) {
      toast.error('Node title cannot be empty');
      return;
    }

    if (isDuplicate(nodes, promptKey, config)) {
      toast.error('A node with the same name and configuration already exists');
      setPreviewNode(null);
      return;
    }

    onAddNode({
      type: 'prompt',
      promptKey,
      config,
    }, { x: CANVAS_CENTER.x, y: CANVAS_CENTER.y });

    setPreviewNode(null);
  };

  const handleNodeDoubleClick = (node: GraphNode) => {
    if (!node.promptKey.trim()) {
      toast.error('Cannot clone node without a name');
      return;
    }
    onAddNode({
      type: node.type,
      promptKey: node.promptKey,
      config: JSON.parse(JSON.stringify(node.config)),
    }, { x: CANVAS_CENTER.x, y: CANVAS_CENTER.y });
  };

  const handleEditNode = (node: GraphNode) => {
    setEditingNode(node);
  };

  const handleEditSave = async (promptKey: string, config: Record<string, unknown>) => {
    if (!editingNode) return;
    if (onUpdateNode) {
      await onUpdateNode(editingNode.id, promptKey, config);
    } else {
      toast.error('Cannot update node');
    }
    setEditingNode(null);
  };

  const handleDeleteNode = (node: GraphNode) => {
    if (onDeleteNode) {
      onDeleteNode(node.id);
    }
  };

  const handleBack = () => {
    if (importStep === 'select-workflow') {
      setImportStep('select-project');
      setWorkflows([]);
    } else if (importStep === 'select-node') {
      setImportStep('select-workflow');
      setAvailableNodes([]);
    } else if (importStep === 'select-project') {
      setImportStep('idle');
      setActiveTab('created');
    }
  };

  if (!visible) return null;

  const renderImportContent = () => {
    if (loading) {
      return (
        <div className="text-center py-4">
          <div className="inline-block w-4 h-4 border-2 border-[var(--bronze-base)] border-t-transparent rounded-full animate-spin" />
          <p className="text-[10px] text-[var(--text-muted)] mt-2">Loading...</p>
        </div>
      );
    }

    switch (importStep) {
      case 'select-project':
        return (
          <div className="space-y-2">
            <div className="flex items-center justify-between">
              <button
                onClick={handleBack}
                className="text-xs text-[var(--text-muted)] hover:text-[var(--bronze-base)]"
              >
                ← Back
              </button>
              <span className="text-[9px] text-[var(--text-muted)]">Select project</span>
            </div>
            {projects.length === 0 ? (
              <div className="text-[10px] text-[var(--text-muted)] text-center py-4">No projects</div>
            ) : (
              projects.map((proj) => (
                <div
                  key={proj.id}
                  className="p-2 bg-[var(--ios-glass-dark)] border border-[var(--ios-border)] rounded text-xs cursor-pointer hover:border-[var(--bronze-base)] transition-colors"
                  onClick={() => handleProjectSelect(proj.id)}
                >
                  <div className="font-semibold text-[var(--bronze-bright)]">{proj.name}</div>
                </div>
              ))
            )}
          </div>
        );

      case 'select-workflow':
        return (
          <div className="space-y-2">
            <div className="flex items-center justify-between">
              <button
                onClick={handleBack}
                className="text-xs text-[var(--text-muted)] hover:text-[var(--bronze-base)]"
              >
                ← Back
              </button>
              <span className="text-[9px] text-[var(--text-muted)]">Select workflow</span>
            </div>
            {workflows.length === 0 ? (
              <div className="text-[10px] text-[var(--text-muted)] text-center py-4">No other workflows</div>
            ) : (
              workflows.map((wf) => (
                <div
                  key={wf.id}
                  className="p-2 bg-[var(--ios-glass-dark)] border border-[var(--ios-border)] rounded text-xs cursor-pointer hover:border-[var(--bronze-base)] transition-colors"
                  onClick={() => handleWorkflowSelect(wf.id)}
                >
                  <div className="font-semibold text-[var(--bronze-bright)]">{wf.name}</div>
                </div>
              ))
            )}
          </div>
        );

      case 'select-node':
        return (
          <div className="space-y-2">
            <div className="flex items-center justify-between">
              <button
                onClick={handleBack}
                className="text-xs text-[var(--text-muted)] hover:text-[var(--bronze-base)]"
              >
                ← Back
              </button>
              <span className="text-[9px] text-[var(--text-muted)]">Select node</span>
            </div>
            {availableNodes.length === 0 ? (
              <div className="text-[10px] text-[var(--text-muted)] text-center py-4">No nodes</div>
            ) : (
              availableNodes.map((node) => (
                <div
                  key={node.node_id}
                  className="p-2 bg-[var(--ios-glass-dark)] border border-[var(--ios-border)] rounded text-xs cursor-pointer hover:border-[var(--bronze-base)] transition-colors"
                  onClick={() => handleNodeSelect(node)}
                >
                  <div className="font-semibold text-[var(--bronze-bright)]">{node.prompt_key}</div>
                  <div className="text-[9px] text-[var(--text-muted)] mt-1">Click to preview</div>
                </div>
              ))
            )}
          </div>
        );

      default:
        return null;
    }
  };

  return (
    <>
      <div className="absolute top-20 right-6 w-80 bg-[var(--ios-glass)] backdrop-blur-md border border-[var(--ios-border)] rounded-lg shadow-[var(--shadow-heavy)] z-[1000]">
        <div className="flex items-center justify-between p-3 border-b border-[var(--ios-border)]">
          <h3 className="text-sm font-bold text-[var(--bronze-base)]">Nodes</h3>
          <button onClick={onClose} className="text-[var(--text-muted)] hover:text-[var(--text-main)]">
            <svg className="w-4 h-4" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
              <line x1="18" y1="6" x2="6" y2="18" />
              <line x1="6" y1="6" x2="18" y2="18" />
            </svg>
          </button>
        </div>
        <div className="flex border-b border-[var(--ios-border)]">
          <button
            onClick={() => setActiveTab('created')}
            className={`flex-1 px-3 py-2 text-xs font-semibold ${
              activeTab === 'created' 
                ? 'bg-[var(--bronze-dim)] text-[var(--bronze-bright)]' 
                : 'text-[var(--text-muted)] hover:bg-[var(--ios-glass-bright)]'
            }`}
          >
            Created ({nodes.length})
          </button>
          <button
            onClick={() => setActiveTab('import')}
            className={`flex-1 px-3 py-2 text-xs font-semibold ${
              activeTab === 'import' 
                ? 'bg-[var(--bronze-dim)] text-[var(--bronze-bright)]' 
                : 'text-[var(--text-muted)] hover:bg-[var(--ios-glass-bright)]'
            }`}
          >
            Import
          </button>
        </div>
        <div className="p-3 max-h-96 overflow-y-auto">
          {activeTab === 'created' ? (
            nodes.length === 0 ? (
              <div className="text-[10px] text-[var(--text-muted)] text-center py-4">No nodes yet</div>
            ) : (
              nodes.map(node => (
                <div
                  key={node.id}
                  className="p-2 mb-2 bg-[var(--ios-glass-dark)] border border-[var(--ios-border)] rounded text-xs cursor-pointer hover:border-[var(--bronze-base)] transition-colors"
                  onDoubleClick={() => handleNodeDoubleClick(node)}
                >
                  <div className="flex items-center justify-between">
                    <div className="font-semibold text-[var(--bronze-bright)]">
                      {node.promptKey || 'Unnamed'}
                    </div>
                    <div className="flex gap-1">
                      <button
                        onClick={(e) => { e.stopPropagation(); handleEditNode(node); }}
                        className="text-[var(--text-muted)] hover:text-[var(--bronze-base)] transition-colors p-1"
                        title="Edit"
                      >
                        <svg className="w-3.5 h-3.5" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                          <path d="M17 3L21 7L7 21H3V17L17 3Z" />
                        </svg>
                      </button>
                      <button
                        onClick={(e) => { e.stopPropagation(); handleDeleteNode(node); }}
                        className="text-[var(--text-muted)] hover:text-[var(--accent-danger)] transition-colors p-1"
                        title="Delete"
                      >
                        <svg className="w-3.5 h-3.5" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                          <line x1="18" y1="6" x2="6" y2="18" />
                          <line x1="6" y1="6" x2="18" y2="18" />
                        </svg>
                      </button>
                    </div>
                  </div>
                  <div className="text-[9px] text-[var(--text-muted)] mt-1">
                    Pos: {Math.round(store.layout.positions[node.id]?.x || 0)}, {Math.round(store.layout.positions[node.id]?.y || 0)}
                  </div>
                </div>
              ))
            )
          ) : (
            importStep === 'idle' ? (
              <div className="text-center py-4">
                <button
                  onClick={handleImportClick}
                  className="px-4 py-2 text-xs font-semibold rounded bg-[var(--bronze-dim)] text-[var(--bronze-bright)] hover:bg-[var(--bronze-base)] hover:text-black transition-colors"
                >
                  Import node
                </button>
              </div>
            ) : (
              renderImportContent()
            )
          )}
        </div>
      </div>

      <EditNodeModal
        isOpen={!!previewNode}
        onClose={() => setPreviewNode(null)}
        initialPromptKey={previewNode?.prompt_key || ''}
        initialConfig={previewNode?.config || {}}
        onSave={handlePreviewSave}
        isSaving={false}
      />

      <EditNodeModal
        isOpen={!!editingNode}
        onClose={() => setEditingNode(null)}
        initialPromptKey={editingNode?.promptKey || ''}
        initialConfig={editingNode?.config || {}}
        onSave={handleEditSave}
        isSaving={false}
      />
    </>
  );
};