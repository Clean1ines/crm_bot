import { Artifact, ArtifactType } from './types';

export interface ArtifactSlice {
  artifacts: Artifact[];
  parentData: Record<string, string>;
  currentArtifact: { content: unknown } | null;
  currentParentId: string | null;
  currentClarificationSessionId: string | null;
  artifactTypes: ArtifactType[];
  selectedArtifactType: string;
  setArtifacts: (artifacts: Artifact[]) => void;
  setCurrentArtifact: (artifact: { content: unknown } | null) => void;
  setCurrentParentId: (id: string | null) => void;
  setCurrentClarificationSessionId: (id: string | null) => void;
  setArtifactTypes: (types: ArtifactType[]) => void;
  setSelectedArtifactType: (type: string) => void;
}

// eslint-disable-next-line @typescript-eslint/no-explicit-any
export const createArtifactSlice = (set: any): ArtifactSlice => ({
  artifacts: [],
  parentData: {},
  currentArtifact: null,
  currentParentId: null,
  currentClarificationSessionId: null,
  artifactTypes: [],
  selectedArtifactType: 'BusinessIdea',
  
  setArtifacts: (artifacts: Artifact[]) => {
    const parentData: Record<string, string> = {};
    artifacts.forEach((a) => {
      parentData[a.id] = a.type;
    });
    set({ artifacts, parentData });
  },
  setCurrentArtifact: (artifact: { content: unknown } | null) => set({ currentArtifact: artifact }),
  setCurrentParentId: (id: string | null) => set({ currentParentId: id }),
  setCurrentClarificationSessionId: (id: string | null) => set({ currentClarificationSessionId: id }),
  setArtifactTypes: (types: ArtifactType[]) => set({ artifactTypes: types }),
  setSelectedArtifactType: (type: string) => set({ selectedArtifactType: type }),
});
