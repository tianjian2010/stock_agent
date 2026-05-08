import { useState } from 'react';
import { useMutation, useQueryClient } from '@tanstack/react-query';
import { api } from '@/lib/api/client';
import type { ChatMessage } from '@/types';

export function useChat(_threadId: string | null) {
  const qc = useQueryClient();
  const [messages, setMessages] = useState<ChatMessage[]>([]);

  const sendMutation = useMutation({
    mutationFn: ({ query, tid }: { query: string; tid?: string }) =>
      api.sendChat(query, tid),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['chatHistory'] });
    },
  });

  return { messages, setMessages, sendMutation };
}