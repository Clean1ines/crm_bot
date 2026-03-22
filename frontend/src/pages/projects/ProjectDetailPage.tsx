import { useParams } from 'react-router-dom';
import { useState } from 'react';
// Исправленные импорты под твою структуру:
import { useProjects } from '@entities/project/api/useProjects'; 
import { DeleteConfirmModal } from '@shared/ui/modal/DeleteConfirmModal';
import { string } from 'three/src/nodes/tsl/TSLCore.js';

export const ProjectDetailPage = () => {
  const { projectId } = useParams();
  // Используем общий хук или достаем один проект из списка
  const { projects, isLoading } = useProjects();
  const project = projects?.find(p => p.id === projectId);
  
  const [isDeleteModalOpen, setIsDeleteModalOpen] = useState(false);

  if (isLoading) return <div className="p-8 text-white">Загрузка...</div>;
  if (!project) return <div className="p-8 text-white">Проект не найден</div>;

  return (
    <div className="p-8 max-w-4xl mx-auto space-y-6 text-white">
      <header className="flex justify-between items-center border-b border-white/10 pb-6">
        <div>
          <h1 className="text-3xl font-bold text-orange-400">{project.name}</h1>
          <p className="text-sm text-gray-400">ID: {project.id}</p>
        </div>
        <button 
          onClick={() => setIsDeleteModalOpen(true)}
          className="text-red-500 hover:text-red-400 text-sm border border-red-500/30 px-3 py-1 rounded"
        >
          🗑️ Удалить проект
        </button>
      </header>

      <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
        <section className="bg-[#1a1a1a] p-6 rounded-xl border border-white/5">
          <h2 className="text-xl mb-4 flex items-center gap-2">🤖 Клиентский бот</h2>
          {(project as any).bot_token ? (
            <div className="space-y-2">
              <p className="text-green-400">✅ Подключен</p>
            </div>
          ) : (
            <div className="space-y-4">
              <input type="text" placeholder="Токен..." className="w-full bg-black border border-white/10 p-2 rounded text-sm" />
              <button className="w-full bg-orange-500 text-black py-2 rounded font-bold">Установить</button>
            </div>
          )}
        </section>
      </div>

      <DeleteConfirmModal 
              isOpen={isDeleteModalOpen}
              onClose={() => setIsDeleteModalOpen(false)}
              onConfirm={async () => { console.log('Deleting...'); } }
              projectName={project.name} 
              itemName={''} 
              itemType={''}      />
    </div>
  );
};
