export const API_BASE_URL = import.meta.env.VITE_API_BASE_URL ?? 'http://localhost:8000';

export const ENDPOINTS = {
  health: '/health',
  chat: '/api/chat',
  chatStream: '/api/chat/stream',
  chatHistory: '/api/chat/history',
  chatStats: '/api/chat/stats',
  adminIndex: '/api/admin/index',
  adminDocuments: '/api/admin/documents',
  adminUploadDocuments: '/api/admin/documents/upload',
  adminReindexSync: '/api/admin/reindex/sync',
} as const;
