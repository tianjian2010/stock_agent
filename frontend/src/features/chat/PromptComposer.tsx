import { useState } from 'react';
import { Send, Square } from 'lucide-react';

interface PromptComposerProps {
  onSend: (query: string) => void;
  onStop?: () => void;
  disabled?: boolean;
  isStreaming?: boolean;
}

export default function PromptComposer({
  onSend,
  onStop,
  disabled,
  isStreaming,
}: PromptComposerProps) {
  const [input, setInput] = useState('');

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    const trimmed = input.trim();
    if (!trimmed || disabled) return;
    onSend(trimmed);
    setInput('');
  };

  return (
    <form onSubmit={handleSubmit} className="border-t border-[var(--border)] bg-[var(--surface)] px-4 py-4 backdrop-blur-xl md:px-6">
      <div className="mx-auto flex max-w-4xl items-end gap-3">
        <textarea
          value={input}
          onChange={(e) => setInput(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === 'Enter' && !e.shiftKey) {
              e.preventDefault();
              handleSubmit(e);
            }
          }}
          placeholder={isStreaming ? '正在生成回答...' : '输入你的研究问题...'}
          disabled={disabled}
          rows={1}
          className="min-h-[48px] flex-1 resize-none rounded-2xl border border-[var(--border)] bg-white/90 px-4 py-3 text-sm text-[var(--text)] placeholder:text-[var(--muted)] shadow-[var(--shadow-soft)] outline-none transition focus:border-[var(--border-strong)] focus:ring-2 focus:ring-[rgba(124,92,58,0.14)] disabled:cursor-not-allowed disabled:bg-[rgba(255,255,255,0.6)]"
          style={{ maxHeight: '160px' }}
        />
        {isStreaming ? (
          <button
            type="button"
            onClick={onStop}
            className="shrink-0 rounded-2xl bg-[#d98b2b] p-3 text-white shadow-[var(--shadow-soft)] transition-colors hover:bg-[#c87a1f]"
            aria-label="停止生成"
          >
            <Square size={18} />
          </button>
        ) : (
          <button
            type="submit"
            disabled={disabled || !input.trim()}
            className="shrink-0 rounded-2xl bg-[#1f2328] p-3 text-white shadow-[var(--shadow-soft)] transition-colors hover:bg-[#373d46] disabled:cursor-not-allowed disabled:bg-[#cfc8bf]"
            aria-label="发送消息"
          >
            <Send size={18} />
          </button>
        )}
      </div>
    </form>
  );
}
