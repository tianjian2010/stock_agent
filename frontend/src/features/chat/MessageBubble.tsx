import ReactMarkdown from 'react-markdown';
import type { ChatMessage } from '@/types';

interface MessageBubbleProps {
  message: ChatMessage;
  isStreaming?: boolean;
}

export default function MessageBubble({ message, isStreaming }: MessageBubbleProps) {
  const isUser = message.role === 'user';

  return (
    <div className={`mb-4 flex ${isUser ? 'justify-end' : 'justify-start'}`}>
      <div
        className={`max-w-[min(70ch,100%)] rounded-3xl px-4 py-3 text-sm leading-relaxed shadow-[var(--shadow-soft)] md:px-5 md:py-4 ${
          isUser
            ? 'rounded-br-md bg-[#1f2328] text-white'
            : 'rounded-bl-md border border-[var(--border)] bg-white/90 text-[var(--text)]'
        }`}
      >
        {isUser ? (
          <p className="whitespace-pre-wrap">{message.content}</p>
        ) : (
          <div className="prose prose-sm max-w-none">
            <ReactMarkdown>{message.content}</ReactMarkdown>
            {isStreaming && <span className="ml-1 inline-block h-4 w-2 animate-pulse rounded bg-[var(--accent-2)]" />}
          </div>
        )}
      </div>
    </div>
  );
}
