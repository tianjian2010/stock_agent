import { useState, useCallback, useRef } from 'react';
import { API_BASE_URL } from '@/lib/constants';
import type { ChatMessage, ChatMetadata, Citation, ToolResult, StreamStatusEvent } from '@/types';

interface StreamCompletePayload {
  threadId: string;
  title?: string;
  message: ChatMessage;
}

interface StreamState {
  threadId?: string;
  title?: string;
}

interface StreamEventPayloads {
  message_start: { thread_id: string; created_at?: string };
  answer_delta: { delta?: string };
  tool_result: ToolResult;
  citations: Citation;
  plan: Record<string, unknown>;
  trace: Record<string, unknown>;
  recovery: Record<string, unknown>;
  status: StreamStatusEvent;
  answer_done: {
    thread_id: string;
    title?: string;
    answer: string;
    citations?: Citation[];
    tool_results?: ToolResult[];
    plan?: Record<string, unknown>;
    trace?: Record<string, unknown>[];
    recovery?: Record<string, unknown>;
    created_at?: string;
  };
  error: { message?: string };
  done: { ok?: boolean };
}

interface UseChatStreamOptions {
  onComplete?: (payload: StreamCompletePayload) => void;
  onThreadReady?: (threadId: string) => void;
}

type StreamingAssistantMessage = ChatMessage & { isStreaming?: boolean };

const STREAMING_PLACEHOLDER: StreamingAssistantMessage = {
  role: 'assistant',
  content: '',
  metadata: {},
  isStreaming: true,
};

function parseSseBlocks(buffer: string): {
  events: Array<{ event: string; data: string }>;
  remainder: string;
} {
  const normalized = buffer.replace(/\r\n/g, '\n');
  const blocks = normalized.split('\n\n');
  const remainder = blocks.pop() ?? '';
  const events = blocks
    .map((block) => {
      const lines = block.split('\n');
      let event = 'message';
      const dataParts: string[] = [];

      for (const line of lines) {
        if (line.startsWith('event:')) {
          event = line.slice(6).trim();
        } else if (line.startsWith('data:')) {
          dataParts.push(line.slice(5).trimStart());
        }
      }

      if (!dataParts.length) return null;
      return { event, data: dataParts.join('\n') };
    })
    .filter((item): item is { event: string; data: string } => item !== null);

  return { events, remainder };
}

export function useChatStream(options: UseChatStreamOptions = {}) {
  const { onComplete, onThreadReady } = options;
  const [messages, setMessages] = useState<StreamingAssistantMessage[]>([]);
  const [isStreaming, setIsStreaming] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [statusEvents, setStatusEvents] = useState<StreamStatusEvent[]>([]);
  const abortControllerRef = useRef<AbortController | null>(null);

  const sendMessage = useCallback(
    async (query: string, threadId?: string) => {
      const userMsg: ChatMessage = { role: 'user', content: query };
      const metadata: ChatMetadata = {
        citations: [],
        tool_results: [],
        trace: [],
      };
      const streamState: StreamState = {
        threadId,
      };

      setError(null);
      setStatusEvents([]);
      setMessages((prev) => [...prev, userMsg, STREAMING_PLACEHOLDER]);
      setIsStreaming(true);
      abortControllerRef.current = new AbortController();

      try {
        const response = await fetch(`${API_BASE_URL}/api/chat/stream`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ query, thread_id: threadId }),
          signal: abortControllerRef.current.signal,
        });

        if (!response.ok) throw new Error(`HTTP ${response.status}`);

        const reader = response.body?.getReader();
        if (!reader) throw new Error('No response body');

        const decoder = new TextDecoder();
        let buffer = '';
        let fullAnswer = '';

        while (true) {
          const { done, value } = await reader.read();
          if (done) break;

          buffer += decoder.decode(value, { stream: true });
          const { events, remainder } = parseSseBlocks(buffer);
          buffer = remainder;

          for (const item of events) {
            let parsed: unknown;
            try {
              parsed = JSON.parse(item.data);
            } catch {
              continue;
            }

            switch (item.event) {
              case 'message_start': {
                const data = parsed as StreamEventPayloads['message_start'];
                if (data.thread_id && data.thread_id !== streamState.threadId) {
                  streamState.threadId = data.thread_id;
                  onThreadReady?.(data.thread_id);
                }
                break;
              }
              case 'answer_delta': {
                const data = parsed as StreamEventPayloads['answer_delta'];
                const delta = data.delta ?? '';
                fullAnswer += delta;
                setMessages((prev) => {
                  const next = [...prev];
                  const lastIdx = next.length - 1;
                  const last = next[lastIdx] as StreamingAssistantMessage | undefined;
                  if (last?.role === 'assistant') {
                    next[lastIdx] = { ...last, content: last.content + delta };
                  }
                  return next;
                });
                break;
              }
              case 'tool_result': {
                const data = parsed as StreamEventPayloads['tool_result'];
                metadata.tool_results = [...(metadata.tool_results ?? []), data];
                break;
              }
              case 'citations': {
                const data = parsed as StreamEventPayloads['citations'];
                metadata.citations = [...(metadata.citations ?? []), data];
                break;
              }
              case 'plan': {
                metadata.plan = parsed as StreamEventPayloads['plan'];
                break;
              }
              case 'trace': {
                metadata.trace = [...(metadata.trace ?? []), parsed as StreamEventPayloads['trace']];
                break;
              }
              case 'recovery': {
                metadata.recovery = parsed as StreamEventPayloads['recovery'];
                break;
              }
              case 'status': {
                const data = parsed as StreamEventPayloads['status'];
                setStatusEvents((prev) => [...prev, data]);
                break;
              }
              case 'answer_done': {
                const data = parsed as StreamEventPayloads['answer_done'];
                streamState.threadId = data.thread_id || streamState.threadId;
                streamState.title = data.title;
                metadata.citations = data.citations ?? metadata.citations;
                metadata.tool_results = data.tool_results ?? metadata.tool_results;
                metadata.plan = data.plan ?? metadata.plan;
                metadata.trace = data.trace ?? metadata.trace;
                metadata.recovery = data.recovery ?? metadata.recovery;
                fullAnswer = data.answer ?? fullAnswer;
                setMessages((prev) => {
                  const next = [...prev];
                  const lastIdx = next.length - 1;
                  const last = next[lastIdx] as StreamingAssistantMessage | undefined;
                  if (last?.role === 'assistant') {
                    next[lastIdx] = {
                      ...last,
                      content: fullAnswer,
                      metadata,
                      created_at: data.created_at,
                      isStreaming: false,
                    };
                  }
                  return next;
                });
                break;
              }
              case 'error': {
                const data = parsed as StreamEventPayloads['error'];
                setError(data.message || 'Stream failed');
                break;
              }
              case 'done': {
                const data = parsed as StreamEventPayloads['done'];
                setMessages((prev) =>
                  prev.map((message) =>
                    (message as StreamingAssistantMessage).isStreaming
                      ? { ...message, content: fullAnswer, metadata, isStreaming: false }
                      : message
                  )
                );
                setIsStreaming(false);

                if (data.ok && streamState.threadId) {
                  onComplete?.({
                    threadId: streamState.threadId,
                    title: streamState.title,
                    message: {
                      role: 'assistant',
                      content: fullAnswer,
                      metadata,
                      created_at: undefined,
                    },
                  });
                }
                break;
              }
              default:
                break;
            }
          }
        }
      } catch (err) {
        if ((err as Error).name === 'AbortError') {
          setMessages((prev) =>
            prev.map((message) =>
              (message as StreamingAssistantMessage).isStreaming
                ? { ...message, isStreaming: false }
                : message
            )
          );
        } else {
          setError((err as Error).message || 'Stream failed');
        }
        setIsStreaming(false);
      }
    },
    [onComplete, onThreadReady]
  );

  const stop = useCallback(() => {
    abortControllerRef.current?.abort();
    setIsStreaming(false);
  }, []);

  return {
    messages: messages as ChatMessage[],
    setMessages,
    isStreaming,
    error,
    statusEvents,
    sendMessage,
    stop,
  };
}
