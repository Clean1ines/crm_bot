import React, { useCallback, useEffect, useState } from 'react';
import { useNavigate, useSearchParams } from 'react-router-dom';
import { useQuery } from '@tanstack/react-query';
import { v4 as uuidv4 } from 'uuid';
import { api } from '@shared/api';
import { IOSShell } from '@/widgets/workflow-shell/ui/IOSShell';
import { IOSCanvas } from '@/widgets/workflow-editor/ui/IOSCanvas';
import { NodeListPanel } from '@/widgets/node-picker/ui/NodeListPanel';
import { NodeModal } from '@/features/node/view-details/ui/NodeModal';
import { useMediaQuery } from '@/shared/lib/hooks/useMediaQuery';
import { HamburgerMenu } from '@/widgets/header/ui/HamburgerMenu';
import { useSelectedProject } from '@/entities/project/api/useSelectedProject';
import { CreateWorkflowModal } from '@/features/workflow/create/ui/CreateWorkflowModal';
import { EditWorkflowModal } from '@/features/workflow/edit/ui/EditWorkflowModal';
import { DeleteConfirmModal } from '@shared/ui';
import { EditNodeModal } from '@/features/node/edit-content/ui/EditNodeModal';
import { SIDEBAR_HAMBURGER_WIDTH } from '@/shared/lib/constants/canvas';
import { useProjects } from '@/entities/project/api/useProjects';
import { useWorkflowStore } from '@/entities/workflow/store/workflowStore';
import { useLoadWorkflow } from '@/entities/workflow/store/useLoadWorkflow';
import { WorkspaceSidebar } from './components/WorkspaceSidebar';
import { NodePickerModal } from '@/widgets/node-picker/ui/NodePickerModal';
import { ModelPickerModal } from '@/features/ai-config/ui/ModelPickerModal';
import { useModels } from '@entities/ai-config/api/useModels';
import { useNotification } from '@/shared/lib/notification/useNotifications';
import { GraphNode } from '@/entities/workflow/store/types';

interface WorkflowSummary {
  id: string;
  name: string;
  description?: string;
}

export const WorkspacePage: React.FC = () => {
  const isMobile = useMediaQuery('(max-width: 768px)');
  const [userClosedSidebar, setUserClosedSidebar] = useState(false);
  const [searchParams, setSearchParams] = useSearchParams();
  const workflowIdFromUrl = searchParams.get('workflowId');
  const navigate = useNavigate();
  const { showNotification } = useNotification();

  const { projects } = useProjects();
  const { selectedProjectId } = useSelectedProject(projects);
  const store = useWorkflowStore();
  const { workflows, currentWorkflowId } = store.ui;

  const { data: workflowsList, isLoading: isLoadingWorkflows } = useQuery({
    queryKey: ['workflows', selectedProjectId],
    queryFn: async () => {
      console.log('[WorkspacePage] fetching workflows for project', selectedProjectId);
      if (!selectedProjectId) return [];
      const { data } = await api.workflows.list(selectedProjectId);
      console.log('[WorkspacePage] workflows loaded:', (data as WorkflowSummary[] | undefined)?.length);
      // Гарантируем, что возвращаем массив
      return Array.isArray(data) ? data : [];
    },
    enabled: !!selectedProjectId,
  });

  // Effect: update store with new list and reset if current workflow not found
  useEffect(() => {
    if (workflowsList) {
      const safeList = Array.isArray(workflowsList) ? workflowsList : [];
      console.log('[WorkspacePage] setting workflows to store, count:', safeList.length);
      useWorkflowStore.getState().setWorkflows(safeList);

      const currentId = useWorkflowStore.getState().ui.currentWorkflowId;
      console.log('[WorkspacePage] current workflow id after set:', currentId);
      if (currentId && !safeList.some(w => w.id === currentId)) {
        console.log('[WorkspacePage] current workflow not in new project, resetting');
        useWorkflowStore.getState().selectWorkflow(null);
        // FIX: clear graph directly instead of calling non-existent method
        useWorkflowStore.setState({ graph: { nodes: [], edges: [] } });
      }
    }
  }, [workflowsList]);

  const { isLoading: isLoadingWorkflow } = useLoadWorkflow(workflowIdFromUrl);

  useEffect(() => {
    console.log('[WorkspacePage] URL workflowId:', workflowIdFromUrl, 'store currentWorkflowId:', currentWorkflowId);
    if (workflowIdFromUrl && workflowIdFromUrl !== currentWorkflowId) {
      console.log('[WorkspacePage] setting store workflow from URL to', workflowIdFromUrl);
      store.selectWorkflow(workflowIdFromUrl);
    }
  }, [workflowIdFromUrl, currentWorkflowId, store]);

  useEffect(() => {
    if (workflows.length > 0 && !currentWorkflowId && !workflowIdFromUrl) {
      const firstId = workflows[0].id;
      console.log('[WorkspacePage] no workflow selected, selecting first:', firstId);
      store.selectWorkflow(firstId);
      setSearchParams({ projectId: selectedProjectId || '', workflowId: firstId });
    }
  }, [workflows, currentWorkflowId, workflowIdFromUrl, selectedProjectId, store, setSearchParams]);

  const handleSelectWorkflow = useCallback((id: string) => {
    console.log('[WorkspacePage] handleSelectWorkflow:', id);
    store.selectWorkflow(id);
    setSearchParams({ projectId: selectedProjectId || '', workflowId: id });
  }, [store, selectedProjectId, setSearchParams]);

  const sidebarOpen = !isMobile && !userClosedSidebar;
  const handleCloseSidebar = () => setUserClosedSidebar(true);
  const handleOpenSidebar = () => setUserClosedSidebar(false);

  const currentProject = projects.find(p => p.id === selectedProjectId);

  const [showCreateModal, setShowCreateModal] = useState(false);
  const [editingWorkflow, setEditingWorkflow] = useState<{ id: string; name: string; description: string } | null>(null);
  const [deletingWorkflow, setDeletingWorkflow] = useState<{ id: string; name: string } | null>(null);
  const [showNodeList, setShowNodeList] = useState(false);
  const [showNodeModal, setShowNodeModal] = useState(false);
  const [editingNode, setEditingNode] = useState<{ id: string; promptKey: string; config: Record<string, unknown> } | null>(null);
  const [deletingNode, setDeletingNode] = useState<{ id: string; name: string } | null>(null);
  const [deletingEdge, setDeletingEdge] = useState<{ edgeId: string; source: string; target: string } | null>(null);

  const [nodeTitle, setNodeTitle] = useState('');
  const [nodePrompt, setNodePrompt] = useState('');
  const [requiresDialogue, setRequiresDialogue] = useState(true); // ADDED for feature X
  const [nodePosition, setNodePosition] = useState<{ x: number; y: number } | null>(null);

  // Состояния для запуска воркфлоу
  const [showNodePicker, setShowNodePicker] = useState(false);
  const [showModelPicker, setShowModelPicker] = useState(false);
  const [selectedStartNode, setSelectedStartNode] = useState<GraphNode | null>(null);
  const [isStartingWorkflow, setIsStartingWorkflow] = useState(false);
  const [selectedWorkflowId, setSelectedWorkflowId] = useState<string | null>(null);

  const { data: models } = useModels();

  const handleStartWorkflow = useCallback((workflowId: string) => {
    setSelectedWorkflowId(workflowId);
    setShowNodePicker(true);
  }, []);

  const startWorkflow = useCallback(async (workflowId: string, node: GraphNode, _model: string) => { // неиспользуемый параметр помечен подчёркиванием
    if (!selectedProjectId) {
      showNotification('No project selected', 'error');
      return;
    }
    if (!node.recordId) {
      showNotification('Node is not fully synced yet. Please wait a moment and try again.', 'error');
      return;
    }
    setIsStartingWorkflow(true);
    try {
      // 1. Создаём Run
      const { data: runData, error: runError } = await api.runs.create({
        project_id: selectedProjectId,
        workflow_id: workflowId,
      });
      if (runError) throw runError;
      const runId = (runData as { id: string }).id;

      // 2. Выполняем стартовый узел (используем recordId)
      const idempotencyKey = uuidv4();
      const { data: execData, error: execError } = await api.runs.executeNode(runId, node.recordId, {
        idempotency_key: idempotencyKey,
        parent_execution_id: null,
        input_artifact_ids: [],
      });
      if (execError) throw execError;
      const executionId = (execData as { id: string }).id;

      // 3. Переходим на страницу чата
      navigate(`/workspace/chat?runId=${runId}&executionId=${executionId}`);
    } catch (err) {
      console.error('[startWorkflow] error:', err);
      showNotification('Failed to start workflow', 'error');
    } finally {
      setIsStartingWorkflow(false);
    }
  }, [selectedProjectId, navigate, showNotification]);

  const handleCreateWorkflow = useCallback(async (name: string, description: string) => {
    console.log('[WorkspacePage] handleCreateWorkflow', { name, description, projectId: selectedProjectId });
    if (!name.trim() || !selectedProjectId) return;
    try {
      const { data } = await api.workflows.create({
        name,
        description,
        project_id: selectedProjectId,
        is_default: false,
      });
      if (data) {
        console.log('[WorkspacePage] workflow created:', data);
        store.setWorkflows([...workflows, { id: (data as { id: string }).id, name, description }]);
        setShowCreateModal(false);
      }
    } catch (error) {
      console.error(error);
    }
  }, [selectedProjectId, workflows, store]);

  const handleUpdateWorkflow = useCallback(async (id: string, name: string, description: string) => {
    console.log('[WorkspacePage] handleUpdateWorkflow', { id, name, description });
    try {
      await api.workflows.update(id, { name, description });
      store.setWorkflows(workflows.map(w => w.id === id ? { ...w, name, description } : w));
      setEditingWorkflow(null);
    } catch (error) {
      console.error(error);
    }
  }, [workflows, store]);

  const handleDeleteWorkflow = useCallback(async (id: string) => {
    console.log('[WorkspacePage] handleDeleteWorkflow', id);
    try {
      await api.workflows.delete(id);
      store.setWorkflows(workflows.filter(w => w.id !== id));
      if (currentWorkflowId === id) {
        store.selectWorkflow(null);
      }
      setDeletingWorkflow(null);
    } catch (error) {
      console.error(error);
    }
  }, [workflows, store, currentWorkflowId]);

  const handleLogout = useCallback(async () => {
    try {
      await api.auth.logout();
      window.location.href = '/login';
    } catch (e) {
      console.error(e);
    }
  }, []);

  const handleOpenCreateModal = useCallback((x: number, y: number) => {
    console.log('[WorkspacePage] open create modal at', { x, y });
    setNodeTitle('');
    setNodePrompt('');
    setRequiresDialogue(true); // ADDED for feature X: reset to default true
    setNodePosition({ x, y });
    setShowNodeModal(true);
  }, []);

  const handleCreateNode = useCallback(() => {
    console.log('[WorkspacePage] handleCreateNode, currentWorkflowId:', currentWorkflowId);
    if (!currentWorkflowId) {
      console.warn('Cannot create node: no workflow selected');
      return;
    }
    const title = nodeTitle.trim() || 'New Node';
    const position = nodePosition || { x: 100, y: 100 };
    console.log('[WorkspacePage] creating node with title:', title, 'position:', position);
    store.addNode(
      { 
        type: 'prompt', 
        promptKey: title, 
        config: { system_prompt: nodePrompt },
        requiresDialogue, // ADDED for feature X
      },
      position
    );
    setShowNodeModal(false);
    setNodePosition(null);
  }, [currentWorkflowId, nodeTitle, nodePrompt, nodePosition, store, requiresDialogue]);

  const handleOpenEditModal = useCallback((nodeId: string) => {
    console.log('[WorkspacePage] open edit modal for node:', nodeId);
    const node = store.graph.nodes.find(n => n.id === nodeId);
    if (node) {
      setEditingNode({ id: node.id, promptKey: node.promptKey, config: node.config });
    }
  }, [store.graph.nodes]);

  const handleRequestDeleteNode = useCallback((nodeId: string) => {
    const node = store.graph.nodes.find(n => n.id === nodeId);
    if (node) {
      setDeletingNode({ id: node.id, name: node.promptKey });
    }
  }, [store.graph.nodes]);

  const handleRequestDeleteEdge = useCallback((edgeId: string) => {
    const edge = store.graph.edges.find(e => e.id === edgeId);
    if (edge) {
      setDeletingEdge({ edgeId, source: edge.source, target: edge.target });
    }
  }, [store.graph.edges]);

  if (isLoadingWorkflows || isLoadingWorkflow) {
    console.log('[WorkspacePage] loading...');
    return <div className="flex items-center justify-center h-screen">Loading...</div>;
  }

  // Добавляем компонент-лоадер перед return
  const LoadingSpinner = () => (
    <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50">
      <div className="animate-spin rounded-full h-12 w-12 border-t-2 border-b-2 border-[var(--bronze-base)]"></div>
    </div>
  );

  return (
    <IOSShell>
      <div className="flex h-full">
        {!sidebarOpen && (
          <HamburgerMenu onOpenSidebar={handleOpenSidebar} showHomeIcon={true} />
        )}

        <WorkspaceSidebar
          isMobile={isMobile}
          sidebarOpen={sidebarOpen}
          onCloseSidebar={handleCloseSidebar}
          onOpenSidebar={handleOpenSidebar}
          selectedProjectId={selectedProjectId}
          currentProjectName={currentProject?.name || ''}
          workflows={workflows}
          currentWorkflowId={currentWorkflowId}
          onSelectWorkflow={handleSelectWorkflow}
          onEditWorkflow={(wf) => setEditingWorkflow({ id: wf.id, name: wf.name, description: wf.description || '' })}
          onDeleteWorkflow={(wf) => setDeletingWorkflow({ id: wf.id, name: wf.name })}
          onCreateWorkflow={() => setShowCreateModal(true)}
          onOpenNodeList={() => setShowNodeList(true)}
          onLogout={handleLogout}
          onStartWorkflow={handleStartWorkflow}
        />

        <div className="flex-1 flex flex-col">
          <div className="h-12 flex items-center border-b border-[var(--ios-border)] bg-[var(--ios-glass-dark)]">
            <div style={{ width: !sidebarOpen ? SIDEBAR_HAMBURGER_WIDTH : 0 }} className="transition-all" />
            <div className="flex-1 flex justify-center items-center">
              <h2 className="text-sm font-semibold text-[var(--text-main)]">
                {workflows.find(w => w.id === currentWorkflowId)?.name || 'Untitled Workflow'}
              </h2>
            </div>
            <div style={{ width: !sidebarOpen ? SIDEBAR_HAMBURGER_WIDTH : 0 }} className="transition-all" />
          </div>
          <IOSCanvas
            onOpenCreateModal={handleOpenCreateModal}
            onOpenEditModal={handleOpenEditModal}
            onRequestDeleteNode={handleRequestDeleteNode}
            onRequestDeleteEdge={handleRequestDeleteEdge}
          />
        </div>

        <NodeListPanel
          visible={showNodeList}
          onClose={() => setShowNodeList(false)}
          nodes={store.graph.nodes}
          onAddNode={(nodeData, position) => {
            store.addNode({
              type: 'prompt',
              promptKey: nodeData.promptKey,
              config: nodeData.config || {},
            }, position);
          }}
          onUpdateNode={async (recordId, promptKey, config) => {
            store.updateNodeConfig(recordId, { promptKey, config });
          }}
          onDeleteNode={(nodeId) => {
            const node = store.graph.nodes.find(n => n.id === nodeId);
            if (node) {
              setDeletingNode({ id: node.id, name: node.promptKey });
            }
          }}
          currentWorkflowId={currentWorkflowId}
        />

        <NodeModal
          visible={showNodeModal}
          onClose={() => setShowNodeModal(false)}
          title={nodeTitle}
          onTitleChange={setNodeTitle}
          prompt={nodePrompt}
          onPromptChange={setNodePrompt}
          requiresDialogue={requiresDialogue}          // ADDED for feature X
          onRequiresDialogueChange={setRequiresDialogue} // ADDED for feature X
          onConfirm={handleCreateNode}
          validationError={
            nodeTitle.trim() ? null : 'Node title cannot be empty'
          }
        />

        <CreateWorkflowModal
          isOpen={showCreateModal}
          onClose={() => setShowCreateModal(false)}
          onCreate={handleCreateWorkflow}
          isPending={false}
        />

        <EditWorkflowModal
          isOpen={!!editingWorkflow}
          onClose={() => setEditingWorkflow(null)}
          initialName={editingWorkflow?.name || ''}
          initialDescription={editingWorkflow?.description || ''}
          onSave={async (name, description) => {
            if (editingWorkflow) {
              await handleUpdateWorkflow(editingWorkflow.id, name, description);
            }
          }}
          isSaving={false}
        />

        <DeleteConfirmModal
          isOpen={!!deletingWorkflow}
          onClose={() => setDeletingWorkflow(null)}
          onConfirm={async () => await handleDeleteWorkflow(deletingWorkflow!.id)}
          itemName={deletingWorkflow?.name || ''}
          itemType="workflow"
          isPending={false}
        />

        <EditNodeModal
          isOpen={!!editingNode}
          onClose={() => setEditingNode(null)}
          initialPromptKey={editingNode?.promptKey || ''}
          initialConfig={editingNode?.config || {}}
          onSave={async (promptKey, config) => {
            if (editingNode) {
              store.updateNodeConfig(editingNode.id, { promptKey, config });
              setEditingNode(null);
            }
          }}
          isSaving={false}
        />

        <DeleteConfirmModal
          isOpen={!!deletingNode}
          onClose={() => setDeletingNode(null)}
          onConfirm={async () => {
            if (deletingNode) {
              store.removeNode(deletingNode.id);
              setDeletingNode(null);
            }
          }}
          itemName={deletingNode?.name || ''}
          itemType="node"
          isPending={false}
        />

        <DeleteConfirmModal
          isOpen={!!deletingEdge}
          onClose={() => setDeletingEdge(null)}
          onConfirm={async () => {
            if (deletingEdge) {
              store.removeEdge(deletingEdge.edgeId);
              setDeletingEdge(null);
            }
          }}
          itemName={`edge`}
          itemType="edge"
          isPending={false}
        />

        {/* Модалка выбора стартового узла */}
        <NodePickerModal
          isOpen={showNodePicker}
          onClose={() => setShowNodePicker(false)}
          nodes={store.graph.nodes}
          onSelect={(node) => {
            setSelectedStartNode(node as GraphNode); // приведение типа
            setShowNodePicker(false);
            setShowModelPicker(true);
          }}
        />

        {/* Модалка выбора модели */}
        <ModelPickerModal
          isOpen={showModelPicker}
          onClose={() => setShowModelPicker(false)}
          models={models || []}
          onSelect={(model) => {
            if (selectedWorkflowId && selectedStartNode) {
              startWorkflow(selectedWorkflowId, selectedStartNode, model);
            }
            setShowModelPicker(false);
          }}
          isPending={isStartingWorkflow}
        />
      </div>
      {isStartingWorkflow && <LoadingSpinner />}
    </IOSShell>
  );
};