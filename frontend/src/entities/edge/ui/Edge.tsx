import React from 'react';
import { GraphEdge } from '@/entities/workflow/store/types';

interface EdgeProps {
  edge: GraphEdge;
  fromPos: { x: number; y: number };
  toPos: { x: number; y: number };
}

export const Edge: React.FC<EdgeProps> = ({ fromPos, toPos }) => {
  console.log('[Edge] rendering', fromPos, toPos);
  return (
    <line
      x1={fromPos.x}
      y1={fromPos.y}
      x2={toPos.x}
      y2={toPos.y}
      stroke="var(--bronze-base)"
      strokeWidth="1.5"
      strokeLinecap="round"
      fill="none"
      filter="url(#glow-line)"
      markerEnd="url(#arrowhead)"
      opacity="0.6"
    />
  );
};