import React from 'react';

export const ComingSoon: React.FC = () => {
  return (
    <div className="flex items-center justify-center h-full">
      <div className="text-center p-8">
        <h1 className="text-2xl font-bold text-[var(--text-primary)] mb-4">В разработке</h1>
        <p className="text-[var(--text-muted)]">Эта страница будет доступна в ближайшее время.</p>
      </div>
    </div>
  );
};
