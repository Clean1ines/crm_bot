import { v5 as uuidv5 } from 'uuid';

const NAMESPACE = '6ba7b810-9dad-11d1-80b4-00c04fd430c8';

export function deterministicNodeId(type: string, promptKey: string, config: Record<string, unknown>): string {
  const hash = JSON.stringify({ type, promptKey, config });
  return uuidv5(hash, NAMESPACE);
}

export function deterministicEdgeId(source: string, target: string): string {
  return uuidv5(`${source}|${target}`, NAMESPACE);
}