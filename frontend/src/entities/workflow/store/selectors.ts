import { useWorkflowStore } from './workflowStore';
import { GraphNode } from './types';

export const useVisibleNodes = (): GraphNode[] => {
  return useWorkflowStore((state) => {
    const { nodes } = state.graph;
    const { positions } = state.layout;
    const { containerWidth, containerHeight } = state;
    const margin = 200;

    const visible: GraphNode[] = [];
    for (const node of nodes) {
      const pos = positions[node.id];
      if (!pos) continue;
      // Проверяем, находится ли узел в пределах видимой области с отступом margin
      if (
        pos.x > -margin &&
        pos.x < containerWidth + margin &&
        pos.y > -margin &&
        pos.y < containerHeight + margin
      ) {
        visible.push(node);
      }
    }
    return visible;
  });
};