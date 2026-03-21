export interface SessionSlice {
  qTokens: string;
  qReq: string;
  isSimpleMode: boolean;
  setTokens: (tokens: string, req: string) => void;
  setSimpleMode: (isSimple: boolean) => void;
}

// eslint-disable-next-line @typescript-eslint/no-explicit-any
export const createSessionSlice = (set: any): SessionSlice => ({
  qTokens: '---',
  qReq: '---',
  isSimpleMode: false,
  setTokens: (tokens: string, req: string) => set({ qTokens: tokens, qReq: req }),
  setSimpleMode: (isSimple: boolean) => set({ isSimpleMode: isSimple }),
});
