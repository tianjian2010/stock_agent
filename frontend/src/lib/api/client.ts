import type {
  AdminDocumentItem,
  AdminIndexStats,
  ChatResponse,
  ChatHistoryResponse,
  CreateChatResponse,
  ReindexResponse,
  ThreadDetailResponse,
  UploadDocumentsResponse,
} from '@/types';

import { API_BASE_URL, ENDPOINTS } from '@/lib/constants';

async function request<T>(path: string, options?: RequestInit): Promise<T> {
  const isFormData = options?.body instanceof FormData;
  const headers = new Headers(options?.headers);
  if (!isFormData && !headers.has('Content-Type')) {
    headers.set('Content-Type', 'application/json');
  }

  const res = await fetch(`${API_BASE_URL}${path}`, {
    ...options,
    headers,
  });
  if (!res.ok) {
    throw new Error(`API error ${res.status}: ${res.statusText}`);
  }
  return res.json() as Promise<T>;
}

export const api = {
  health: () => request<{ status: string }>(ENDPOINTS.health),

  sendChat: (query: string, threadId?: string) =>
    request<ChatResponse>(ENDPOINTS.chat, {
      method: 'POST',
      body: JSON.stringify({ query, thread_id: threadId }),
    }),

  getHistory: () => request<ChatHistoryResponse>(ENDPOINTS.chatHistory),

  getThread: (threadId: string) =>
    request<ThreadDetailResponse>(`${ENDPOINTS.chatHistory}/${threadId}`),

  createThread: (title?: string) =>
    request<CreateChatResponse>(ENDPOINTS.chatHistory, {
      method: 'POST',
      body: JSON.stringify({ title }),
    }),

  deleteThread: (threadId: string) =>
    request<{ status: string; thread_id: string }>(`${ENDPOINTS.chatHistory}/${threadId}`, {
      method: 'DELETE',
    }),

  getStats: () =>
    request<{ document_count: number; chunk_count: number; vector_ready: boolean }>(
      ENDPOINTS.chatStats
    ),

  getAdminIndex: () => request<AdminIndexStats>(ENDPOINTS.adminIndex),

  getAdminDocuments: (keyword?: string) =>
    request<AdminDocumentItem[]>(
      keyword
        ? `${ENDPOINTS.adminDocuments}?keyword=${encodeURIComponent(keyword)}`
        : ENDPOINTS.adminDocuments
    ),

  reindexDocumentsSync: () =>
    request<ReindexResponse>(ENDPOINTS.adminReindexSync, {
      method: 'POST',
    }),

  uploadDocuments: (files: File[], overwrite = false) => {
    const form = new FormData();
    files.forEach((file) => {
      form.append('files', file);
    });
    form.append('overwrite', String(overwrite));

    return request<UploadDocumentsResponse>(ENDPOINTS.adminUploadDocuments, {
      method: 'POST',
      body: form,
    });
  },
};
