import { create } from 'zustand';
import { persist } from 'zustand/middleware';

import { ArtifactSlice, createArtifactSlice } from '@entities/artifact/model/artifact.slice';
import { AiConfigSlice, createAiConfigSlice } from '@entities/ai-config/model/config.slice';
import { ChatSlice, createChatSlice } from '@entities/chat/model/chat.slice';
import { SessionSlice, createSessionSlice } from '@entities/session/model/session.slice';

export * from '@entities/artifact/model/types';
export * from '@entities/ai-config/model/types';
export * from '@entities/chat/model/types';

export type AppState = ArtifactSlice & AiConfigSlice & ChatSlice & SessionSlice;

export const useAppStore = create<AppState>()(
  persist(
    (set) => ({
      ...createArtifactSlice(set),
      ...createAiConfigSlice(set),
      ...createChatSlice(set),
      ...createSessionSlice(set),
    }),
    {
      name: 'mrak-ui-state',
      partialize: (state) => ({
        selectedModel: state.selectedModel,
        selectedArtifactType: state.selectedArtifactType,
        isSimpleMode: state.isSimpleMode,
      }),
    }
  )
);
