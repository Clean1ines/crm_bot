export interface SessionSlice {
  qTokens: string;
  qReq: string;
  isSimpleMode: boolean;
  setTokens: (tokens: string, req: string) => void;
  setSimpleMode: (isSimple: boolean) => void;
}

type SessionSet = (partial: Partial<SessionSlice>) => void;

export const createSessionSlice = (set: SessionSet): SessionSlice => ({
  qTokens: '---',
  qReq: '---',
  isSimpleMode: false,
  setTokens: (tokens: string, req: string) => set({ qTokens: tokens, qReq: req }),
  setSimpleMode: (isSimple: boolean) => set({ isSimpleMode: isSimple }),
});
