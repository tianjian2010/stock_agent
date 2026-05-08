import { Activity } from 'lucide-react';

export interface TraceStep {
  name: string;
  status: string;
  detail: string;
  data?: Record<string, unknown>;
}

export interface PlanData {
  intent: string;
  direct_answer_mode?: string | null;
  use_document_search: boolean;
  planned_tools: { name: string; query: string; reason: string }[];
  notes: string[];
  stages: {
    stage_id: string;
    stage_type: string;
    title: string;
    goal: string;
    worker: string;
    query: string;
    depends_on: string[];
  }[];
  planner_source: string;
}

interface TracePanelProps {
  plan?: PlanData;
  trace?: TraceStep[];
}

const STATUS_COLORS: Record<string, string> = {
  completed: 'text-[#10b981]',
  failed: 'text-[#ef4444]',
  skipped: 'text-[#f59e0b]',
  in_progress: 'text-[#6366f1]',
};

function StatusDot({ status }: { status: string }) {
  const colorClass = STATUS_COLORS[status] || 'text-[#9ca3af]';
  return <span className={`inline-block h-2 w-2 rounded-full bg-current ${colorClass}`} />;
}

function PlanSummary({ plan }: { plan: PlanData }) {
  return (
    <div className="space-y-3 rounded-2xl border border-[var(--border)] bg-white/70 p-4">
      <div className="space-y-1">
        <p className="text-[10px] uppercase tracking-[0.24em] text-[var(--muted)]">Intent</p>
        <p className="text-sm text-[var(--text)]">{plan.intent || '-'}</p>
      </div>
      <div className="flex flex-wrap items-center gap-2 text-xs text-[var(--muted)]">
        <span className="rounded-full bg-[rgba(56,87,106,0.08)] px-2.5 py-1 text-[var(--accent-2)]">
          {plan.planner_source}
        </span>
        {plan.direct_answer_mode && (
          <span className="rounded-full bg-[rgba(124,92,58,0.08)] px-2.5 py-1 text-[var(--accent)]">
            {plan.direct_answer_mode}
          </span>
        )}
      </div>
      {plan.stages.length > 0 && (
        <div className="space-y-2">
          <p className="text-xs text-[var(--muted)]">执行阶段</p>
          <ul className="space-y-2">
            {plan.stages.map((stage, index) => (
              <li key={stage.stage_id || index} className="flex items-start gap-2 text-xs">
                <span className="font-mono text-[var(--accent-soft)]">{index + 1}.</span>
                <div>
                  <p className="font-medium text-[var(--text)]">{stage.title}</p>
                  <p className="text-[var(--muted)]">{stage.worker}</p>
                </div>
              </li>
            ))}
          </ul>
        </div>
      )}
    </div>
  );
}

function TraceList({ trace }: { trace: TraceStep[] }) {
  return (
    <ul className="space-y-2">
      {trace.map((step, index) => (
        <li key={`${step.name}-${index}`} className="flex items-start gap-2 text-xs">
          <StatusDot status={step.status} />
          <div className="min-w-0 flex-1">
            <p className="truncate font-medium text-[var(--text)]">{step.name}</p>
            <p className="mt-0.5 line-clamp-2 text-[var(--muted)]">{step.detail}</p>
          </div>
        </li>
      ))}
    </ul>
  );
}

export function TracePanel({ plan, trace }: TracePanelProps) {
  if (!plan && !trace) return null;

  return (
    <div className="border-t border-[var(--border)]">
      <div className="flex items-center gap-2 px-4 py-3">
        <Activity size={12} className="text-[var(--accent-2)]" />
        <span className="text-xs font-semibold uppercase tracking-[0.24em] text-[var(--muted)]">
          执行轨迹
        </span>
      </div>
      <div className="space-y-4 px-4 pb-4">
        {plan && <PlanSummary plan={plan} />}
        {trace && trace.length > 0 && (
          <div className="rounded-2xl border border-[var(--border)] bg-white/70 p-4">
            <p className="mb-2 text-xs text-[var(--muted)]">步骤 ({trace.length})</p>
            <TraceList trace={trace} />
          </div>
        )}
      </div>
    </div>
  );
}
