import type { MouseEvent } from 'react';
import { useLocation, useNavigate } from 'react-router-dom';
import { FolderOpen, MessageSquare, Plus, Trash2 } from 'lucide-react';

import { useChatHistory, useCreateThread, useDeleteThread } from '@/hooks/useChatHistory';

export default function SidebarChatHistory() {
  const { data: chats = [], isLoading } = useChatHistory();
  const deleteThread = useDeleteThread();
  const createThread = useCreateThread();
  const navigate = useNavigate();
  const location = useLocation();
  const onDocumentsPage = location.pathname.startsWith('/documents');

  const handleNewChat = () => {
    createThread.mutate(undefined, {
      onSuccess: (data) => {
        navigate(`/chat/${data.thread_id}`);
      },
    });
  };

  const handleDelete = (e: MouseEvent, threadId: string) => {
    e.stopPropagation();
    deleteThread.mutate(threadId);
  };

  return (
    <aside className="hidden h-full w-64 flex-col border-r border-[var(--border)] bg-[#faf9f5] md:flex">
      <div className="border-b border-[var(--border)] px-4 py-5">
        <div className="space-y-2">
          <button
            onClick={handleNewChat}
            className="inline-flex w-full items-center justify-center gap-2 rounded-2xl bg-[#1f2328] px-3 py-2.5 text-sm font-medium text-white shadow-[var(--shadow-soft)] transition-colors hover:bg-[#373d46]"
          >
            <Plus size={16} />
            新建对话
          </button>
          <button
            onClick={() => navigate('/documents')}
            className={`inline-flex w-full items-center justify-center gap-2 rounded-2xl border px-3 py-2.5 text-sm font-medium transition-colors ${
              onDocumentsPage
                ? 'border-[#cab79d] bg-[#efe4d3] text-[#3f3122]'
                : 'border-[var(--border)] bg-white/80 text-[var(--muted)] hover:border-[var(--border-strong)] hover:text-[var(--text)]'
            }`}
          >
            <FolderOpen size={16} />
            资料管理
          </button>
        </div>
      </div>

      <div className="flex-1 overflow-y-auto px-2 py-3">
        {isLoading ? (
          <p className="px-2 text-sm text-[var(--muted)]">加载中...</p>
        ) : chats.length === 0 ? (
          <p className="px-2 text-sm text-[var(--muted)]">暂无历史会话</p>
        ) : (
          <ul className="space-y-1">
            {chats.map((chat) => (
              <li key={chat.thread_id}>
                <div
                  className="group flex cursor-pointer items-center gap-2 rounded-2xl px-3 py-2 transition-colors hover:bg-[rgba(255,255,255,0.8)]"
                  onClick={() => navigate(`/chat/${chat.thread_id}`)}
                >
                  <MessageSquare size={14} className="shrink-0 text-[var(--muted)]" />
                  <span className="flex-1 truncate text-sm text-[var(--text)]">
                    {chat.title || '新对话'}
                  </span>
                  <button
                    onClick={(e) => handleDelete(e, chat.thread_id)}
                    className="rounded-lg p-1 text-[#ef4444] opacity-0 transition-opacity hover:bg-[#fde8e8] group-hover:opacity-100"
                    aria-label="删除会话"
                  >
                    <Trash2 size={12} />
                  </button>
                </div>
              </li>
            ))}
          </ul>
        )}
      </div>
    </aside>
  );
}
