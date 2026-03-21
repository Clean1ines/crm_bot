export interface ChatMessageData {
  role: 'user' | 'assistant';
  content: string;
  timestamp: number;
}
