import { useModels } from '@/entities/ai-config/api/useModels';
import { useModes } from '@/entities/ai-config/api/useModes';
import { useArtifactTypes } from '@/entities/artifact/api/useArtifactTypes';
import { useArtifacts } from '@/entities/artifact/api/useArtifacts';
import { useMessages } from '@/entities/chat/api/useMessages';

/**
 * Хук-агрегатор для инициализации всех данных проекта.
 * Вызывает хуки загрузки моделей, режимов, типов артефактов,
 * а также артефактов и сообщений для текущего проекта.
 * 
 * Используется в ProtectedLayout для предварительной загрузки данных.
 */
export const useProjectData = () => {
  // Загружаем статические данные
  useModels();
  useModes();
  useArtifactTypes();

  // Загружаем динамические данные для текущего проекта
  useArtifacts();
  useMessages();

  // Ничего не возвращаем, данные автоматически попадают в store
};
