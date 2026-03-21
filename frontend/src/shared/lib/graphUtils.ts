import { GraphNode, GraphEdge } from '@/entities/workflow/store/types';

type Color = 0 | 1 | 2;
const WHITE: Color = 0;
const GRAY: Color = 1;
const BLACK: Color = 2;

interface CycleResult {
  hasCycle: boolean;
  cyclePath?: string[];
}

export function hasCycle(nodes: GraphNode[], edges: GraphEdge[]): CycleResult {
  const adjacency: Map<string, string[]> = new Map();
  const nodeIdSet = new Set(nodes.map(n => n.id));

  for (const node of nodes) {
    adjacency.set(node.id, []);
  }

  for (const edge of edges) {
    if (nodeIdSet.has(edge.source) && nodeIdSet.has(edge.target)) {
      const targets = adjacency.get(edge.source) || [];
      targets.push(edge.target);
      adjacency.set(edge.source, targets);
    }
  }

  const color: Map<string, Color> = new Map();
  const parent: Map<string, string | null> = new Map();

  for (const nodeId of nodeIdSet) {
    color.set(nodeId, WHITE);
    parent.set(nodeId, null);
  }

  let cyclePath: string[] | undefined;

  function dfs(nodeId: string): boolean {
    color.set(nodeId, GRAY);

    const neighbors = adjacency.get(nodeId) || [];
    for (const neighbor of neighbors) {
      const neighborColor = color.get(neighbor);

      if (neighborColor === GRAY) {
        cyclePath = reconstructCycle(nodeId, neighbor, parent);
        return true;
      }

      if (neighborColor === WHITE) {
        parent.set(neighbor, nodeId);
        if (dfs(neighbor)) return true;
      }
    }

    color.set(nodeId, BLACK);
    return false;
  }

  function reconstructCycle(current: string, cycleStart: string, parent: Map<string, string | null>): string[] {
    const path: string[] = [cycleStart];
    let node: string | null = current;
    while (node !== null && node !== cycleStart) {
      path.unshift(node);
      node = parent.get(node) || null;
    }
    path.unshift(cycleStart);
    return path;
  }

  for (const nodeId of nodeIdSet) {
    if (color.get(nodeId) === WHITE) {
      if (dfs(nodeId)) return { hasCycle: true, cyclePath };
    }
  }

  return { hasCycle: false };
}

export function formatCycleDescription(cyclePath: string[], nodes: GraphNode[]): string {
  if (!cyclePath || cyclePath.length < 2) {
    return 'Detected a cycle in the workflow';
  }

  const nodeMap = new Map(nodes.map(n => [n.id, n.promptKey]));
  const labels = cyclePath.map(id => nodeMap.get(id) || id);

  if (labels.length <= 5) {
    return `Cycle detected: ${labels.join(' → ')}`;
  }

  return `Cycle detected: ${labels.slice(0, 3).join(' → ')} → ... → ${labels[labels.length - 1]}`;
}

export function validateWorkflowAcyclic(nodes: GraphNode[], edges: GraphEdge[]): { valid: boolean; error?: string } {
  const result = hasCycle(nodes, edges);

  if (result.hasCycle && result.cyclePath) {
    const description = formatCycleDescription(result.cyclePath, nodes);
    return { valid: false, error: description };
  }

  return { valid: true };
}
