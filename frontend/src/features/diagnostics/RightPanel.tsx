import { useQuery } from '@tanstack/react-query';
import { Database, FileStack } from 'lucide-react';

import { api } from '@/lib/api/client';
import { CitationPanel, ToolResultPanel } from '@/features/citations/CitationPanel';
import { TracePanel } from '@/features/diagnostics/TracePanel';
import { RecoveryBanner } from '@/features/diagnostics/RecoveryBanner';
import type { Citation, ToolResult } from '@/types';
import type { PlanData, TraceStep } from '@/features/diagnostics/TracePanel';

interface RightPanelProps {
  citations: Citation[];
  toolResults: ToolResult[];
  plan?: PlanData;
  trace?: TraceStep[];
  recovery?: Record<string, unknown>;
  isOpen: boolean;
}

function DocStats() {
  const { data: stats } = useQuery({
    queryKey: ['stats'],
    queryFn: api.getStats,
  });

  return (
    <div className="border-t border-[var(--border)] px-4 py-4">
      <h3 className="mb-3 flex items-center gap-2 text-[10px] font-semibold uppercase tracking-[0.24em] text-[var(--muted)]">
        <Database size={12} />
        资料库状态
      </h3>
      <div className="space-y-2 text-xs text-[var(--muted)]">
        <div className="flex items-center justify-between rounded-xl bg-[#faf7f0] px-3 py-2">
          <div className="flex items-center gap-2">
            <FileStack size={12} />
            <span>文档</span>
          </div>
          <span className="font-medium text-[var(--text)]">{stats?.document_count ?? '-'}</span>
        </div>
        <div className="flex items-center justify-between rounded-xl bg-[#faf7f0] px-3 py-2">
          <span>向量检索</span>
          <span className="font-medium text-[var(--text)]">{stats?.vector_ready ? '可用' : '未就绪'}</span>
        </div>
      </div>
    </div>
  );
}

export function RightPanel({
  citations,
  toolResults,
  plan,
  trace,
  recovery,
  isOpen,
}: RightPanelProps) {
  if (!isOpen) return null;

  return (
    <aside className="fixed inset-y-0 right-0 z-40 w-[min(90vw,22rem)] overflow-y-auto border-l border-[var(--border)] bg-[rgba(255,253,248,0.96)] shadow-[var(--shadow)] backdrop-blur-xl lg:static lg:flex lg:w-80 lg:shadow-none">
      <div className="sticky top-0 border-b border-[var(--border)] bg-[rgba(255,253,248,0.96)] px-4 py-4 backdrop-blur-xl">
        <p className="mb-1 text-[10px] uppercase tracking-[0.28em] text-[var(--muted)]">Research Feed</p>
        <p className="text-sm text-[var(--text)]">引用、工具、轨迹与恢复信息集中展示</p>
      </div>

      <RecoveryBanner recovery={recovery as Record<string, unknown> | undefined} />

      <div className="flex-1 py-2">
        <CitationPanel citations={citations} />
        <ToolResultPanel toolResults={toolResults} />
        <TracePanel plan={plan} trace={trace} />
      </div>

      <DocStats />
    </aside>
  );
}
