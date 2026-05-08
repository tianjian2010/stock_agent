import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { api } from '@/lib/api/client';
import type { ChatHistoryItem } from '@/types';

export function useChatHistory() {
  return useQuery<ChatHistoryItem[]>({
    queryKey: ['chatHistory'],
    queryFn: async () => {
      const res = await api.getHistory();
      return res.chats;
    },
  });
}

export function useDeleteThread() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: api.deleteThread,
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['chatHistory'] });
    },
  });
}

export function useCreateThread() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (title?: string) => api.createThread(title),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['chatHistory'] });
    },
  });
}