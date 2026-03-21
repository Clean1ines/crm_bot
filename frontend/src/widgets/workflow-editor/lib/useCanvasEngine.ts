// frontend/src/widgets/workflow-editor/lib/useCanvasEngine.ts
import { useState, useCallback, useRef, useEffect } from 'react';
import { useWorkflowStore } from '@/entities/workflow/store/workflowStore';

export interface UseCanvasEngineReturn {
  handleNodeDragStart: (nodeId: string, e: React.MouseEvent | React.TouchEvent, element: HTMLDivElement) => void;
  draggedNodeId: string | null;
  draggedNodePosition: { x: number; y: number } | null;
}

export const useCanvasEngine = (): UseCanvasEngineReturn => {
  const store = useWorkflowStore();
  const positions = store.layout.positions;
  const moveNode = store.moveNode;

  const [draggedNode, setDraggedNode] = useState<string | null>(null);
  const [draggedNodePosition, setDraggedNodePosition] = useState<{ x: number; y: number } | null>(null);

  const draggedElement = useRef<HTMLDivElement | null>(null);
  const startWorldPos = useRef({ x: 0, y: 0 });
  const startScreenPos = useRef({ x: 0, y: 0 });

  const getClientCoords = (e: MouseEvent | TouchEvent | React.MouseEvent | React.TouchEvent): { x: number; y: number } => {
    if ('touches' in e && e.touches.length > 0) {
      return { x: e.touches[0].clientX, y: e.touches[0].clientY };
    }
    if ('clientX' in e) {
      return { x: e.clientX, y: e.clientY };
    }
    return { x: 0, y: 0 };
  };

  useEffect(() => {
    if (!draggedNode || !draggedElement.current) return;

    const element = draggedElement.current;
    const prevUserSelect = document.body.style.userSelect;
    const prevCursor = document.body.style.cursor;
    document.body.style.userSelect = 'none';
    document.body.style.cursor = 'grabbing';

    const handleGlobalMove = (e: MouseEvent | TouchEvent): void => {
      e.preventDefault();
      const { x, y } = getClientCoords(e);
      const deltaScreenX = x - startScreenPos.current.x;
      const deltaScreenY = y - startScreenPos.current.y;
      const newWorldX = startWorldPos.current.x + deltaScreenX;
      const newWorldY = startWorldPos.current.y + deltaScreenY;

      const { containerWidth, containerHeight, layout } = useWorkflowStore.getState();
      const size = layout.sizes[draggedNode];
      const maxX = containerWidth - (size?.width ?? 0);
      const maxY = containerHeight - (size?.height ?? 0);
      let clampedX = newWorldX;
      let clampedY = newWorldY;
      if (containerWidth > 0 && containerHeight > 0) {
        clampedX = Math.max(0, Math.min(newWorldX, maxX));
        clampedY = Math.max(0, Math.min(newWorldY, maxY));
      }

      element.style.transform = `translate3d(${clampedX}px, ${clampedY}px, 0)`;
      setDraggedNodePosition({ x: clampedX, y: clampedY });
    };

    const handleGlobalEnd = (): void => {
      const finalWorldX = parseFloat(element.style.transform.split('(')[1]?.split('px')[0] || '0');
      const finalWorldY = parseFloat(element.style.transform.split(',')[1]?.split('px')[0] || '0');

      moveNode(draggedNode, { x: finalWorldX, y: finalWorldY });

      setDraggedNode(null);
      setDraggedNodePosition(null);
      draggedElement.current = null;
      document.body.style.userSelect = prevUserSelect;
      document.body.style.cursor = prevCursor;
      window.removeEventListener('mousemove', handleGlobalMove);
      window.removeEventListener('mouseup', handleGlobalEnd);
      window.removeEventListener('touchmove', handleGlobalMove);
      window.removeEventListener('touchend', handleGlobalEnd);
    };

    const passiveOpts = { passive: false } as AddEventListenerOptions;
    window.addEventListener('mousemove', handleGlobalMove, passiveOpts);
    window.addEventListener('mouseup', handleGlobalEnd);
    window.addEventListener('touchmove', handleGlobalMove, passiveOpts);
    window.addEventListener('touchend', handleGlobalEnd);

    return () => {
      window.removeEventListener('mousemove', handleGlobalMove);
      window.removeEventListener('mouseup', handleGlobalEnd);
      window.removeEventListener('touchmove', handleGlobalMove);
      window.removeEventListener('touchend', handleGlobalEnd);
      document.body.style.userSelect = prevUserSelect;
      document.body.style.cursor = prevCursor;
    };
  }, [draggedNode, moveNode]);

  const handleNodeDragStart = useCallback((nodeId: string, e: React.MouseEvent | React.TouchEvent, element: HTMLDivElement): void => {
    console.log('[useCanvasEngine] handleNodeDragStart', nodeId);
    e.stopPropagation();
    e.preventDefault();

    const pos = positions[nodeId];
    if (!pos) return;

    const { x, y } = getClientCoords(e);

    startWorldPos.current = pos;
    startScreenPos.current = { x, y };
    draggedElement.current = element;
    setDraggedNode(nodeId);
    setDraggedNodePosition(pos);
    store.selectNode(nodeId);
  }, [positions, store]);

  return {
    handleNodeDragStart,
    draggedNodeId: draggedNode,
    draggedNodePosition,
  };
};