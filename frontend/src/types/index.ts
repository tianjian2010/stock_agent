export type ChatRole = 'user' | 'assistant';

export interface Citation {
  filename: string;
  published_at?: string | null;
  snippet?: string | null;
  topic?: string | null;
  chunk_id?: number | null;
  total_chunks?: number | null;
}

export interface ToolResult {
  name: string;
  success: boolean;
  recovered: boolean;
  degraded: boolean;
  error_message: string;
  reason: string;
  content: string;
}

export interface ChatMetadata {
  citations?: Citation[];
  tool_results?: ToolResult[];
  plan?: Record<string, unknown>;
  trace?: Record<string, unknown>[];
  recovery?: Record<string, unknown>;
}

export interface StreamStatusEvent {
  event: string;
  payload: Record<string, unknown>;
}

export interface ChatMessage {
  id?: number;
  role: ChatRole;
  content: string;
  metadata?: ChatMetadata;
  created_at?: string;
}

export interface ChatResponse {
  thread_id: string;
  title: string;
  answer: string;
  citations: Citation[];
  tool_results: ToolResult[];
  plan: Record<string, unknown>;
  trace: Record<string, unknown>[];
  recovery: Record<string, unknown>;
  created_at: string;
}

export interface MessageItem {
  id: number;
  role: ChatRole;
  content: string;
  created_at: string;
  metadata: Record<string, unknown>;
}

export interface ThreadDetailResponse {
  thread_id: string;
  title: string | null;
  messages: MessageItem[];
}

export interface ChatHistoryItem {
  thread_id: string;
  title: string | null;
  created_at: string;
  updated_at: string;
}

export interface ChatHistoryResponse {
  chats: ChatHistoryItem[];
}

export interface CreateChatResponse {
  thread_id: string;
  id: number;
}

export interface AdminIndexStats {
  document_count: number;
  chunk_count: number;
  vector_ready: boolean;
  indexed: boolean;
}

export interface AdminDocumentItem {
  filename: string;
  topic: string;
  published_at: string;
  source: string;
  size: number;
  file_type: string;
}

export interface ReindexResponse {
  status: string;
  document_count: number;
  chunk_count: number;
  vector_ready: boolean;
  updated_files: number;
  removed_files: number;
}

export interface UploadResultItem {
  filename: string;
  status: string;
  detail: string;
}

export interface UploadDocumentsResponse {
  saved: UploadResultItem[];
  skipped: UploadResultItem[];
  index_result: ReindexResponse;
}
