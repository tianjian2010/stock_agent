import { useState, useEffect, useCallback } from 'react';
import { useNavigate, useParams, useSearchParams } from 'react-router-dom';
import { useQuery, useQueryClient } from '@tanstack/react-query';
import { History, PanelRightOpen, Plus, Sparkles, X } from 'lucide-react';

import { api } from '@/lib/api/client';
import type { ChatMessage, ChatMetadata, Citation, ToolResult } from '@/types';
import type { PlanData, TraceStep } from '@/features/diagnostics/TracePanel';
import SidebarChatHistory from '@/features/history/SidebarChatHistory';
import MessageList from '@/features/chat/MessageList';
import PromptComposer from '@/features/chat/PromptComposer';
import StreamStatusBar from '@/features/chat/StreamStatusBar';
import { RightPanel } from '@/features/diagnostics/RightPanel';
import { useChatStream } from '@/hooks/useChatStream';

function extractDiagnostics(metadata?: ChatMetadata): {
  citations: Citation[];
  toolResults: ToolResult[];
  plan: PlanData | undefined;
  trace: TraceStep[];
  recovery: Record<string, unknown> | undefined;
} {
  return {
    citations: metadata?.citations || [],
    toolResults: metadata?.tool_results || [],
    plan: metadata?.plan as PlanData | undefined,
    trace: ((metadata?.trace || []) as unknown) as TraceStep[],
    recovery: metadata?.recovery,
  };
}

export default function ChatPage() {
  const { threadId } = useParams<{ threadId: string }>();
  const [searchParams] = useSearchParams();
  const navigate = useNavigate();
  const qc = useQueryClient();

  const [rightPanelOpen, setRightPanelOpen] = useState(false);
  const [citations, setCitations] = useState<Citation[]>([]);
  const [toolResults, setToolResults] = useState<ToolResult[]>([]);
  const [plan, setPlan] = useState<PlanData | undefined>();
  const [trace, setTrace] = useState<TraceStep[]>([]);
  const [recovery, setRecovery] = useState<Record<string, unknown> | undefined>();
  const [titleOverride, setTitleOverride] = useState<string | null>(null);

  const { data: threadData } = useQuery({
    queryKey: ['thread', threadId],
    queryFn: () => api.getThread(threadId!),
    enabled: !!threadId && threadId !== 'new',
  });

  const handleComplete = useCallback(
    ({
      threadId: completedThreadId,
      title,
      message,
    }: {
      threadId: string;
      title?: string;
      message: ChatMessage;
    }) => {
      const next = extractDiagnostics(message.metadata);
      setCitations(next.citations);
      setToolResults(next.toolResults);
      setPlan(next.plan);
      setTrace(next.trace);
      setRecovery(next.recovery);
      if (title) setTitleOverride(title);
      qc.invalidateQueries({ queryKey: ['thread', completedThreadId] });
      qc.invalidateQueries({ queryKey: ['chatHistory'] });
    },
    [qc]
  );

  const handleThreadReady = useCallback(
    (resolvedThreadId: string) => {
      if (threadId === 'new') {
        navigate(`/chat/${resolvedThreadId}`, { replace: true });
      }
    },
    [navigate, threadId]
  );

  const { messages, setMessages, isStreaming, error, statusEvents, sendMessage, stop } =
    useChatStream({
      onComplete: handleComplete,
      onThreadReady: handleThreadReady,
    });

  useEffect(() => {
    setMessages([]);
    setCitations([]);
    setToolResults([]);
    setPlan(undefined);
    setTrace([]);
    setRecovery(undefined);
    setTitleOverride(null);
    setRightPanelOpen(false);
  }, [threadId, setMessages]);

  useEffect(() => {
    if (!threadData?.messages || threadId === 'new') return;

    const loaded: ChatMessage[] = threadData.messages.map((message) => ({
      id: message.id,
      role: message.role as 'user' | 'assistant',
      content: message.content,
      metadata: message.metadata as ChatMetadata,
      created_at: message.created_at,
    }));

    setMessages(loaded);
    setTitleOverride(threadData.title || null);

    const lastAssistant = [...loaded].reverse().find((message) => message.role === 'assistant');
    const next = extractDiagnostics(lastAssistant?.metadata);
    setCitations(next.citations);
    setToolResults(next.toolResults);
    setPlan(next.plan);
    setTrace(next.trace);
    setRecovery(next.recovery);
  }, [threadData, threadId, setMessages]);

  useEffect(() => {
    if (threadId !== 'new') return;

    const query = searchParams.get('query');
    if (query && messages.length === 0) {
      sendMessage(query);
    }
  }, [messages.length, searchParams, sendMessage, threadId]);

  const handleSend = useCallback(
    (query: string) => {
      sendMessage(query, threadId !== 'new' ? threadId : undefined);
    },
    [sendMessage, threadId]
  );

  const hasDiagnostics =
    citations.length > 0 || toolResults.length > 0 || !!plan || trace.length > 0 || !!recovery;
  const currentTitle = titleOverride || threadData?.title || '新对话';
  const statusVisible = isStreaming && statusEvents.length > 0;
  const handleNewChat = useCallback(() => {
    navigate('/chat/new');
  }, [navigate]);

  return (
    <div className="relative flex min-h-screen overflow-hidden">
      <SidebarChatHistory />

      <div className="flex min-w-0 flex-1 flex-col">
        <header className="shrink-0 border-b border-[var(--border)] bg-[var(--surface)] px-4 py-3 shadow-[0_1px_0_rgba(255,255,255,0.45)] backdrop-blur-xl md:px-6">
          <div className="flex items-center gap-3">
            <div className="flex min-w-0 items-center gap-3">
              <div className="flex h-10 w-10 items-center justify-center rounded-full bg-[#1a1714] text-white shadow-lg">
                <Sparkles size={16} />
              </div>
              <div className="min-w-0">
                <h2 className="truncate text-sm font-semibold text-[var(--text)]">{currentTitle}</h2>
                <p className="truncate text-xs text-[var(--muted)]">股票研究工作台 · 资料、行情、资讯与选股</p>
              </div>
            </div>

            <div className="ml-auto flex items-center gap-2 md:hidden">
              <button
                onClick={handleNewChat}
                className="inline-flex items-center gap-2 rounded-full border border-[var(--border)] bg-white/75 px-3 py-2 text-xs text-[var(--muted)] shadow-[var(--shadow-soft)]"
              >
                <Plus size={14} />
                新建
              </button>
              <button
                onClick={() => navigate('/')}
                className="inline-flex items-center gap-2 rounded-full border border-[var(--border)] bg-white/75 px-3 py-2 text-xs text-[var(--muted)] shadow-[var(--shadow-soft)]"
              >
                <History size={14} />
                首页
              </button>
            </div>

            {error && (
              <span className="rounded-full border border-[#f0c8bf] bg-[#fff0ec] px-3 py-1.5 text-xs text-[#b23c2f]">
                流式请求失败: {error}
              </span>
            )}

            {hasDiagnostics && (
              <button
                onClick={() => setRightPanelOpen(!rightPanelOpen)}
                className="ml-auto inline-flex items-center gap-2 rounded-full border border-[var(--border)] bg-white/70 px-3 py-2 text-xs text-[var(--muted)] transition-colors hover:border-[var(--border-strong)] hover:text-[var(--text)]"
              >
                <PanelRightOpen size={14} />
                {rightPanelOpen ? '隐藏详情' : '显示详情'}
              </button>
            )}
          </div>
        </header>

        <StreamStatusBar events={statusEvents} visible={statusVisible} />

        <MessageList messages={messages} isStreaming={isStreaming} />

        <PromptComposer
          onSend={handleSend}
          onStop={stop}
          disabled={isStreaming}
          isStreaming={isStreaming}
        />
      </div>

      <RightPanel
        isOpen={rightPanelOpen}
        citations={citations}
        toolResults={toolResults}
        plan={plan}
        trace={trace}
        recovery={recovery}
      />

      {rightPanelOpen && (
        <button
          type="button"
          aria-label="关闭详情面板"
          onClick={() => setRightPanelOpen(false)}
          className="fixed inset-0 z-30 bg-[rgba(18,16,13,0.28)] backdrop-blur-[1px] lg:hidden"
        >
          <span className="absolute right-4 top-4 inline-flex items-center gap-2 rounded-full border border-[var(--border)] bg-white/90 px-3 py-2 text-xs text-[var(--muted)] shadow-[var(--shadow-soft)]">
            <X size={14} />
            关闭
          </span>
        </button>
      )}
    </div>
  );
}
