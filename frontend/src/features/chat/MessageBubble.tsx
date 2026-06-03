import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import type { ChatMessage } from '@/types';

interface MessageBubbleProps {
  message: ChatMessage;
  isStreaming?: boolean;
}

export default function MessageBubble({ message, isStreaming }: MessageBubbleProps) {
  const isUser = message.role === 'user';
  const assistantContent = !isUser
    ? message.content.replace(/\[资料(\d+)\]/g, (_, num: string) => `[资料${num}](#citation-${num})`)
    : message.content;

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
            <ReactMarkdown
              remarkPlugins={[remarkGfm]}
              components={{
                a: ({ href, children }) => {
                  const isCitationLink = typeof href === 'string' && href.startsWith('#citation-');
                  if (!isCitationLink) {
                    return (
                      <a href={href} className="text-[var(--accent-2)] underline underline-offset-2">
                        {children}
                      </a>
                    );
                  }
                  return (
                    <a
                      href={href}
                      className="font-medium text-[var(--accent-2)] underline underline-offset-2"
                      onClick={(event) => {
                        event.preventDefault();
                        const target = document.querySelector(href);
                        target?.scrollIntoView({ behavior: 'smooth', block: 'start' });
                        if (target instanceof HTMLElement) {
                          target.classList.add('ring-2', 'ring-[var(--accent-2)]');
                          window.setTimeout(() => {
                            target.classList.remove('ring-2', 'ring-[var(--accent-2)]');
                          }, 1600);
                        }
                      }}
                    >
                      {children}
                    </a>
                  );
                },
                table: ({ children }) => (
                  <div className="markdown-table-wrap">
                    <table className="markdown-table">{children}</table>
                  </div>
                ),
              }}
            >
              {assistantContent}
            </ReactMarkdown>
            {isStreaming && <span className="ml-1 inline-block h-4 w-2 animate-pulse rounded bg-[var(--accent-2)]" />}
          </div>
        )}
      </div>
    </div>
  );
}
