import type { StreamStatusEvent } from '@/types';

interface StreamStatusBarProps {
  events: StreamStatusEvent[];
  visible?: boolean;
}

function formatStatus(event: StreamStatusEvent): string {
  switch (event.event) {
    case 'planning':
      return `正在规划任务 · ${String(event.payload.planner_source ?? 'agent')}`;
    case 'memory_loaded':
      return `正在加载记忆 · ${event.payload.has_memory ? '命中历史上下文' : '无历史上下文'}`;
    case 'documents_indexed':
      return '正在准备资料索引';
    case 'tasks_built':
      return `已拆分任务 · ${String(event.payload.task_count ?? 0)} 个任务 / ${String(event.payload.batch_count ?? 0)} 个批次`;
    case 'batch_started':
      return `执行批次 ${String(event.payload.batch_id ?? 0)}`;
    case 'batch_finished':
      return `批次 ${String(event.payload.batch_id ?? 0)} 完成`;
    case 'evidence_ready':
      return `证据已就绪 · ${String(event.payload.citation_count ?? 0)} 条引用 / ${String(event.payload.tool_result_count ?? 0)} 条工具结果`;
    case 'direct_answer_ready':
      return '已命中直答模式';
    default:
      return event.event;
  }
}

export default function StreamStatusBar({ events, visible }: StreamStatusBarProps) {
  if (!visible || events.length === 0) return null;

  const latest = events[events.length - 1];

  return (
    <div className="border-b border-[var(--border)] bg-[rgba(255,253,248,0.92)] px-4 py-3 backdrop-blur-xl md:px-6">
      <div className="flex items-center gap-3">
        <span className="inline-flex h-2.5 w-2.5 animate-pulse rounded-full bg-[var(--accent-2)] shadow-[0_0_0_6px_rgba(56,87,106,0.08)]" />
        <p className="text-sm text-[var(--muted)]">{formatStatus(latest)}</p>
      </div>
      {events.length > 1 && (
        <div className="mt-2 flex flex-wrap gap-2">
          {events.slice(-4).map((event, index) => (
            <span
              key={`${event.event}-${index}`}
              className="rounded-full border border-[var(--border)] bg-white/80 px-2.5 py-1 text-xs text-[var(--muted)]"
            >
              {formatStatus(event)}
            </span>
          ))}
        </div>
      )}
    </div>
  );
}
