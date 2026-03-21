import React, { useState, useEffect, useRef } from 'react';
import { GraphNode, GraphEdge } from '@/entities/workflow/store/types';
import { useWorkflowStore } from '@/entities/workflow/store/workflowStore';

interface StarNodeProps {
  node: GraphNode;
  position: { x: number; y: number };
  edges: GraphEdge[];
  allNodes: GraphNode[];
  isSelected: boolean;
  isConnecting?: boolean;
  onDragStart: (nodeId: string, e: React.MouseEvent | React.TouchEvent, element: HTMLDivElement) => void;
  onEdit: (nodeId: string) => void;
  onStartConnection: (nodeId: string) => void;
  onNodeClick: (nodeId: string) => void;
  onRequestDelete: (nodeId: string) => void;
  onRequestDeleteEdge?: (edgeId: string) => void;
}

export const IOSNode = React.forwardRef<HTMLDivElement, StarNodeProps>(({
  node,
  position,
  edges,
  allNodes,
  isSelected,
  isConnecting = false,
  onDragStart,
  onEdit,
  onStartConnection,
  onNodeClick,
  onRequestDelete,
  onRequestDeleteEdge,
}, ref) => {
  const [showEdgeMenu, setShowEdgeMenu] = useState(false);
  const updateNodeSize = useWorkflowStore(state => state.updateNodeSize);
  const labelGroupRef = useRef<HTMLDivElement>(null);

  const connectedEdges = edges.filter(e => e.source === node.id || e.target === node.id);
  const connections = connectedEdges.map(e => {
    const otherNodeId = e.source === node.id ? e.target : e.source;
    const otherNode = allNodes.find(n => n.id === otherNodeId);
    return {
      edgeId: e.id,
      otherNodeName: otherNode?.promptKey || otherNodeId.substring(0, 6),
    };
  });

  // Измеряем размеры группы при монтировании и при изменении текста
  useEffect(() => {
    if (labelGroupRef.current) {
      const rect = labelGroupRef.current.getBoundingClientRect();
      // Добавляем небольшой отступ, чтобы не было впритык
      updateNodeSize(node.id, { width: rect.width + 4, height: rect.height + 4 });
    }
  }, [node.promptKey, updateNodeSize, node.id]);

  const handleDoubleClick = (e: React.MouseEvent) => {
    e.stopPropagation();
    onEdit(node.id);
  };

  const handleClick = (e: React.MouseEvent) => {
    console.log('[IOSNode] onNodeClick', node.id);
    e.stopPropagation();
    onNodeClick(node.id);
  };

  const handleEdgeMenuClick = (e: React.MouseEvent) => {
    e.stopPropagation();
    setShowEdgeMenu(!showEdgeMenu);
  };

  const handleStartConnection = (e: React.MouseEvent) => {
    console.log('[IOSNode] onStartConnection', node.id);
    e.stopPropagation();
    onStartConnection(node.id);
  };

  const handleDeleteClick = (e: React.MouseEvent) => {
    e.stopPropagation();
    onRequestDelete(node.id);
  };

  return (
    <div
      ref={ref}
      className="absolute"
      style={{
        transform: `translate3d(${position.x}px, ${position.y}px, 0) translate(-50%, -50%)`,
        left: 0,
        top: 0,
        userSelect: 'none',
      }}
      onMouseDown={(e) => onDragStart(node.id, e, e.currentTarget)}
      onTouchStart={(e) => onDragStart(node.id, e, e.currentTarget)}
      onDoubleClick={handleDoubleClick}
      onClick={handleClick}
    >
      <div
        className={`rounded-full bg-[var(--bronze-base)] transition-all duration-200 ${
          isSelected ? 'w-4 h-4 bg-[var(--bronze-bright)]' : 'w-3 h-3'
        } ${isConnecting ? 'ring-2 ring-[var(--bronze-bright)] ring-offset-2' : ''}`}
        style={{
          position: 'absolute',
          left: 0,
          top: 0,
          transform: 'translate(-50%, -50%)',
          pointerEvents: 'none',
        }}
      />

      <div
        ref={labelGroupRef}
        style={{
          position: 'absolute',
          left: 8,
          top: '50%',
          transform: 'translateY(-50%)',
          display: 'flex',
          alignItems: 'center',
          gap: 4,
          pointerEvents: 'auto',
          whiteSpace: 'nowrap',
        }}
      >
        <span className="text-xs font-mono text-[var(--text-main)]">
          {node.promptKey}
        </span>
        <button
          onClick={handleStartConnection}
          className="text-[var(--bronze-bright)] hover:text-[var(--bronze-base)] transition-colors"
          title="Start connection"
        >
          <svg className="w-3 h-3" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
            <line x1="12" y1="5" x2="12" y2="19" />
            <line x1="5" y1="12" x2="19" y2="12" />
          </svg>
        </button>
        {connectedEdges.length > 0 && (
          <button
            onClick={handleEdgeMenuClick}
            className="text-[var(--text-muted)] hover:text-[var(--accent-danger)] transition-colors"
            title="Manage connections"
          >
            <svg className="w-3 h-3" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
              <line x1="5" y1="12" x2="19" y2="12" />
            </svg>
          </button>
        )}
        <button
          onClick={handleDeleteClick}
          className="text-[var(--text-muted)] hover:text-[var(--accent-danger)] transition-colors"
          title="Delete node"
        >
          <svg className="w-3 h-3" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
            <line x1="18" y1="6" x2="6" y2="18" />
            <line x1="6" y1="6" x2="18" y2="18" />
          </svg>
        </button>
      </div>

      {showEdgeMenu && (
        <div
          className="absolute bg-[var(--ios-glass-dark)] border border-[var(--ios-border)] rounded shadow-lg z-10 p-1"
          style={{
            left: 8,
            top: '100%',
            marginTop: 4,
          }}
        >
          {connections.map(conn => (
            <div key={conn.edgeId} className="flex items-center justify-between p-1 hover:bg-[var(--ios-glass-bright)]">
              <span className="text-xs truncate">{conn.otherNodeName}</span>
              <button
                onClick={(e) => {
                  e.stopPropagation();
                  if (onRequestDeleteEdge) onRequestDeleteEdge(conn.edgeId);
                  setShowEdgeMenu(false);
                }}
                className="text-[var(--text-muted)] hover:text-[var(--accent-danger)]"
              >
                ✕
              </button>
            </div>
          ))}
        </div>
      )}
    </div>
  );
});

IOSNode.displayName = 'IOSNode';