import React from 'react';
import { Zap } from 'lucide-react';

type LlmUsageCardProps = {
  visible: boolean;
  usageText: string;
};

export const LlmUsageCard: React.FC<LlmUsageCardProps> = ({
  visible,
  usageText,
}) => {
  if (!visible) return null;

  return (
    <div className="min-w-0 rounded-xl bg-[var(--surface-secondary)] p-3">
      <div className="mb-1 flex items-center gap-1 font-medium text-[var(--text-primary)]">
        <Zap className="h-3.5 w-3.5" />
        ИИ
      </div>
      <div className="text-[var(--text-muted)]">{usageText}</div>
    </div>
  );
};
