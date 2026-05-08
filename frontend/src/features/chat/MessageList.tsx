import { useEffect, useRef } from 'react';

import type { ChatMessage } from '@/types';
import MessageBubble from './MessageBubble';

interface MessageListProps {
  messages: ChatMessage[];
  isStreaming?: boolean;
}

export default function MessageList({ messages, isStreaming }: MessageListProps) {
  const bottomRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages, isStreaming]);

  const hasStreamingMsg = messages.some((message) => (message as { isStreaming?: boolean }).isStreaming);

  return (
    <div className="flex-1 overflow-y-auto px-4 py-6 md:px-6">
      {messages.length === 0 && !isStreaming ? (
        <div className="flex h-full flex-col items-center justify-center text-center">
          <div className="mb-4 flex h-14 w-14 items-center justify-center rounded-full border border-[var(--border)] bg-white/70 shadow-[var(--shadow-soft)]">
            <span className="h-3 w-3 rounded-full bg-[var(--accent-2)] opacity-80" />
          </div>
          <p className="text-sm text-[var(--muted)]">围绕 A 股投资资料、行情、资讯进行对话式研究</p>
          <p className="mt-1 text-xs text-[#8a8174]">可以问：最近有哪些研究报、量子方向怎么看、宁德时代最新价</p>
        </div>
      ) : (
        <>
          {messages.map((message, idx) => (
            <MessageBubble
              key={message.id ?? idx}
              message={message}
              isStreaming={(message as { isStreaming?: boolean }).isStreaming}
            />
          ))}
          {isStreaming && !hasStreamingMsg && (
            <div className="mb-4 flex justify-start">
              <div className="rounded-3xl rounded-bl-md border border-[var(--border)] bg-white/90 px-4 py-3 shadow-[var(--shadow-soft)]">
                <div className="flex gap-1.5">
                  <span className="h-2 w-2 animate-bounce rounded-full bg-[rgba(111,103,91,0.3)]" style={{ animationDelay: '0ms' }} />
                  <span className="h-2 w-2 animate-bounce rounded-full bg-[rgba(111,103,91,0.3)]" style={{ animationDelay: '150ms' }} />
                  <span className="h-2 w-2 animate-bounce rounded-full bg-[rgba(111,103,91,0.3)]" style={{ animationDelay: '300ms' }} />
                </div>
              </div>
            </div>
          )}
          <div ref={bottomRef} />
        </>
      )}
    </div>
  );
}
