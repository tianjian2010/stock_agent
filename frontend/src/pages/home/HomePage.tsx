import { useNavigate } from 'react-router-dom';
import { FileText, MessageSquare, TrendingUp } from 'lucide-react';

import { useChatHistory } from '@/hooks/useChatHistory';
import type { ChatHistoryItem } from '@/types';

const SUGGESTIONS = [
  { icon: FileText, text: '最近有哪些新研究报？' },
  { icon: TrendingUp, text: '量子计算方向怎么看？' },
  { icon: MessageSquare, text: '宁德时代最新价是多少？' },
];

export default function HomePage() {
  const navigate = useNavigate();
  const { data: chats = [] } = useChatHistory();
  const recentChats = (chats as ChatHistoryItem[]).slice(0, 4);

  return (
    <div className="flex min-h-screen flex-col bg-[radial-gradient(circle_at_top,_rgba(255,255,255,0.8),_transparent_36%),linear-gradient(180deg,var(--bg)_0%,var(--bg-2)_100%)]">
      <header className="px-4 py-14 text-center md:py-16">
        <p className="mb-3 text-xs uppercase tracking-[0.34em] text-[var(--muted)]">Stock Research Desk</p>
        <h1 className="text-4xl font-semibold text-[var(--text)] md:text-5xl">股票投研 Agent</h1>
        <p className="mx-auto mt-3 max-w-2xl text-sm text-[var(--muted)]">
          本地投研资料 + 实时行情 + 资讯检索的对话式工作台
        </p>
      </header>

      <main className="flex flex-1 flex-col items-center px-4 pb-12">
        {recentChats.length === 0 && (
          <div className="mb-8 rounded-3xl border border-[var(--border)] bg-white/70 px-5 py-4 text-center text-sm text-[var(--muted)] shadow-[var(--shadow-soft)]">
            还没有会话，先试试下面的快捷问题，或者直接输入你的研究主题。
          </div>
        )}

        {recentChats.length > 0 && (
          <section className="mb-8 w-full max-w-3xl">
            <h3 className="mb-3 text-left text-sm font-medium text-[var(--muted)]">最近会话</h3>
            <div className="grid grid-cols-1 gap-3 md:grid-cols-2">
              {recentChats.map((chat) => (
                <button
                  key={chat.thread_id}
                  onClick={() => navigate(`/chat/${chat.thread_id}`)}
                  className="flex items-center gap-3 rounded-2xl border border-[var(--border)] bg-white/75 px-4 py-3 text-left shadow-[var(--shadow-soft)] transition-colors hover:border-[var(--border-strong)]"
                >
                  <MessageSquare size={16} className="shrink-0 text-[var(--accent-2)]" />
                  <span className="truncate text-sm text-[var(--text)]">{chat.title || '新对话'}</span>
                </button>
              ))}
            </div>
          </section>
        )}

        <section className="mb-12 flex max-w-2xl flex-wrap justify-center gap-3">
          {SUGGESTIONS.map(({ icon: Icon, text }) => (
            <button
              key={text}
              onClick={() => navigate(`/chat/new?query=${encodeURIComponent(text)}`)}
              className="flex items-center gap-2 rounded-2xl border border-[var(--border)] bg-white/75 px-4 py-2 text-sm text-[var(--text)] shadow-[var(--shadow-soft)] transition-colors hover:border-[var(--border-strong)]"
            >
              <Icon size={16} className="text-[var(--accent-2)]" />
              {text}
            </button>
          ))}
        </section>

        <section className="w-full max-w-2xl">
          <input
            type="text"
            placeholder="输入你的研究问题..."
            className="w-full rounded-2xl border border-[var(--border)] bg-white/90 px-4 py-3 text-[var(--text)] shadow-[var(--shadow-soft)] outline-none transition focus:border-[var(--border-strong)] focus:ring-2 focus:ring-[rgba(124,92,58,0.14)]"
            onKeyDown={(e) => {
              if (e.key === 'Enter' && e.currentTarget.value.trim()) {
                navigate(`/chat/new?query=${encodeURIComponent(e.currentTarget.value.trim())}`);
              }
            }}
          />
        </section>
      </main>
    </div>
  );
}
