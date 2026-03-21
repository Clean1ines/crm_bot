import { GraphNode } from '@/entities/workflow/store/types';

export const useNodeValidation = (nodes: GraphNode[]) => {
  const validateNodeUnique = (title: string, prompt: string): string | null => {
    const exists = nodes.some(
      node => node.promptKey === title && node.config?.system_prompt === prompt
    );
    return exists ? 'Node with same name and prompt already exists' : null;
  };

  return { validateNodeUnique };
};
