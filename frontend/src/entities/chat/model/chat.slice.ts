import { ChatMessageData } from './types';

export interface ChatSlice {
  messages: ChatMessageData[];
  setMessages: (messages: ChatMessageData[]) => void;
  addMessage: (message: ChatMessageData) => void;
}

// eslint-disable-next-line @typescript-eslint/no-explicit-any
export const createChatSlice = (set: any): ChatSlice => ({
  messages: [],
  setMessages: (messages: ChatMessageData[]) => set({ messages }),
  addMessage: (msg: ChatMessageData) => set((state: ChatSlice) => ({ messages: [...state.messages, msg] })),
});
