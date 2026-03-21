// frontend/src/widgets/workflow-editor/ui/IOSCanvas.tsx
import React, { useRef, useCallback, useState, useMemo, useEffect } from 'react';
import { useWorkflowStore } from '@/entities/workflow/store/workflowStore';
import { IOSNode } from '@/entities/node/ui/Node';
import { Edge } from '@/entities/edge/ui/Edge';
import { useCanvasEngine } from '../lib/useCanvasEngine';

interface IOSCanvasProps {
  onOpenCreateModal?: (x: number, y: number) => void;
  onOpenEditModal?: (nodeId: string) => void;
  onRequestDeleteNode?: (nodeId: string) => void;
  onRequestDeleteEdge?: (edgeId: string) => void;
}

export const IOSCanvas: React.FC<IOSCanvasProps> = ({
  onOpenCreateModal,
  onOpenEditModal,
  onRequestDeleteNode,
  onRequestDeleteEdge,
}) => {
  const containerRef = useRef<HTMLDivElement>(null);
  const [connectingNode, setConnectingNode] = useState<string | null>(null);
  const [mousePos, setMousePos] = useState<{ x: number; y: number } | null>(null);

  const {
    handleNodeDragStart,
    draggedNodeId,
    draggedNodePosition,
  } = useCanvasEngine();

  const visibleNodes = useWorkflowStore(state => state.graph.nodes);
  const edges = useWorkflowStore(state => state.graph.edges);
  const positions = useWorkflowStore(state => state.layout.positions);
  const selectedNodeId = useWorkflowStore(state => state.ui.selectedNodeId);
  const addEdge = useWorkflowStore(state => state.addEdge);
  const setContainerSize = useWorkflowStore(state => state.setContainerSize);

  // Обновляем размеры контейнера при изменении окна или сайдбара
  useEffect(() => {
    const updateSize = () => {
      if (containerRef.current) {
        const rect = containerRef.current.getBoundingClientRect();
        setContainerSize(rect.width, rect.height);
      }
    };
    updateSize();
    window.addEventListener('resize', updateSize);
    // также следим за изменением сайдбара (можно добавить observer)
    const observer = new ResizeObserver(updateSize);
    if (containerRef.current) observer.observe(containerRef.current);
    return () => {
      window.removeEventListener('resize', updateSize);
      observer.disconnect();
    };
  }, [setContainerSize]);

  const handleMouseMove = useCallback((e: MouseEvent) => {
    if (!containerRef.current || !connectingNode) return;
    const rect = containerRef.current.getBoundingClientRect();
    const worldX = e.clientX - rect.left;
    const worldY = e.clientY - rect.top;
    setMousePos({ x: worldX, y: worldY });
  }, [connectingNode]);

  useEffect(() => {
    if (!connectingNode) {
      setMousePos(null);
    }
  }, [connectingNode]);

  useEffect(() => {
    if (connectingNode) {
      window.addEventListener('mousemove', handleMouseMove);
      return () => {
        window.removeEventListener('mousemove', handleMouseMove);
      };
    }
  }, [connectingNode, handleMouseMove]);

  const handleNodeClick = useCallback((nodeId: string) => {
    console.log('[IOSCanvas] handleNodeClick', nodeId);
    if (connectingNode && connectingNode !== nodeId) {
      addEdge(connectingNode, nodeId);
      setConnectingNode(null);
      setMousePos(null);
    } else if (connectingNode === nodeId) {
      setConnectingNode(null);
      setMousePos(null);
    }
  }, [connectingNode, addEdge]);

  const handleBackgroundClick = useCallback((e: React.MouseEvent) => {
    if (e.target === containerRef.current) {
      setConnectingNode(null);
      setMousePos(null);
    }
  }, []);

  const edgeElements = useMemo(() => {
    return edges.map(edge => {
      const fromNode = visibleNodes.find(n => n.id === edge.source);
      const toNode = visibleNodes.find(n => n.id === edge.target);
      if (!fromNode || !toNode) return null;

      let fromPos = positions[edge.source];
      let toPos = positions[edge.target];
      if (edge.source === draggedNodeId && draggedNodePosition) {
        fromPos = draggedNodePosition;
      }
      if (edge.target === draggedNodeId && draggedNodePosition) {
        toPos = draggedNodePosition;
      }
      if (!fromPos || !toPos) return null;

      return (
        <Edge
          key={edge.id}
          edge={edge}
          fromPos={fromPos}
          toPos={toPos}
        />
      );
    });
  }, [edges, visibleNodes, positions, draggedNodeId, draggedNodePosition]);

  const connectionLine = useMemo(() => {
    if (!connectingNode) return null;
    const fromPos = positions[connectingNode];
    if (!fromPos) return null;
    const toPos = mousePos || { x: 0, y: 0 };
    return (
      <line
        x1={fromPos.x}
        y1={fromPos.y}
        x2={toPos.x}
        y2={toPos.y}
        stroke="var(--bronze-bright)"
        strokeWidth="1.5"
        strokeDasharray="5,5"
        opacity="0.8"
      />
    );
  }, [connectingNode, positions, mousePos]);

  const getCanvasCoords = useCallback((clientX: number, clientY: number) => {
    if (!containerRef.current) return { x: 0, y: 0 };
    const rect = containerRef.current.getBoundingClientRect();
    return {
      x: clientX - rect.left,
      y: clientY - rect.top,
    };
  }, []);

  const handleDoubleClick = useCallback((e: React.MouseEvent) => {
    e.preventDefault();
    e.stopPropagation();
    if (onOpenCreateModal) {
      const { x, y } = getCanvasCoords(e.clientX, e.clientY);
      onOpenCreateModal(x, y);
    }
  }, [getCanvasCoords, onOpenCreateModal]);

  return (
    <div
      ref={containerRef}
      className="flex-1 relative overflow-hidden bg-[var(--bg-canvas)] cursor-crosshair"
      onDoubleClick={handleDoubleClick}
      onClick={handleBackgroundClick}
    >
      <svg className="absolute top-0 left-0 w-full h-full" style={{ pointerEvents: 'none' }}>
        <defs>
          <marker id="arrowhead" markerWidth="10" markerHeight="7" refX="9" refY="3.5" orient="auto">
            <polygon points="0 0, 10 3.5, 0 7" fill="var(--bronze-base)" />
          </marker>
          <filter id="glow-line" x="-20%" y="-20%" width="140%" height="140%">
            <feGaussianBlur stdDeviation="2" result="blur" />
            <feMerge>
              <feMergeNode in="blur" />
              <feMergeNode in="SourceGraphic" />
            </feMerge>
          </filter>
        </defs>
        {edgeElements}
        {connectionLine}
      </svg>

      <div style={{ pointerEvents: 'auto' }}>
        {visibleNodes.map(node => (
          <IOSNode
            key={node.id}
            node={node}
            position={positions[node.id]}
            edges={edges}
            allNodes={visibleNodes}
            isSelected={selectedNodeId === node.id}
            isConnecting={connectingNode === node.id}
            onDragStart={handleNodeDragStart}
            onEdit={onOpenEditModal || (() => {})}
            onStartConnection={() => setConnectingNode(node.id)}
            onNodeClick={handleNodeClick}
            onRequestDelete={onRequestDeleteNode || (() => {})}
            onRequestDeleteEdge={onRequestDeleteEdge || (() => {})}
          />
        ))}
      </div>
    </div>
  );
};