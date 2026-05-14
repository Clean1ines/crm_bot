import { t } from '../shared/i18n';
import React from 'react';

export const ComingSoon: React.FC = () => {
  return (
    <div className="flex items-center justify-center h-full">
      <div className="p-4 text-center sm:p-6 lg:p-8">
        <h1 className="mb-4 text-2xl font-semibold leading-tight text-[var(--text-primary)]">{t('comingSoon.title')}</h1>
        <p className="text-[var(--text-muted)]">{t('comingSoon.description')}</p>
      </div>
    </div>
  );
};
