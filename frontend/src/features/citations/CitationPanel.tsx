import { AlertTriangle, CheckCircle, FileText, XCircle } from 'lucide-react';

import type { Citation, ToolResult } from '@/types';

interface CitationPanelProps {
  citations: Citation[];
}

export function CitationPanel({ citations }: CitationPanelProps) {
  if (!citations.length) return null;

  return (
    <div className="border-t border-[var(--border)]">
      <h3 className="px-4 py-3 text-xs font-semibold uppercase tracking-[0.24em] text-[var(--muted)]">
        引用资料 ({citations.length})
      </h3>
      <ul className="space-y-2 px-4 pb-4">
        {citations.map((citation, idx) => (
          <li key={`${citation.filename}-${idx}`} className="flex items-start gap-2 text-sm">
            <FileText size={14} className="mt-0.5 shrink-0 text-[var(--accent-2)]" />
            <div>
              <p className="text-[var(--text)]">{citation.filename}</p>
              {citation.published_at && <p className="text-xs text-[var(--muted)]">{citation.published_at}</p>}
            </div>
          </li>
        ))}
      </ul>
    </div>
  );
}

interface ToolResultPanelProps {
  toolResults: ToolResult[];
}

function ToolStatusIcon({ result }: { result: ToolResult }) {
  if (result.error_message) return <XCircle size={14} className="text-[#ef4444]" />;
  if (result.degraded) return <AlertTriangle size={14} className="text-[#f59e0b]" />;
  if (result.recovered) return <CheckCircle size={14} className="text-[#10b981]" />;
  return <CheckCircle size={14} className="text-[#10b981]" />;
}

export function ToolResultPanel({ toolResults }: ToolResultPanelProps) {
  if (!toolResults.length) return null;

  return (
    <div className="border-t border-[var(--border)]">
      <h3 className="px-4 py-3 text-xs font-semibold uppercase tracking-[0.24em] text-[var(--muted)]">
        工具调用 ({toolResults.length})
      </h3>
      <ul className="space-y-2 px-4 pb-4">
        {toolResults.map((result, idx) => (
          <li key={`${result.name}-${idx}`} className="text-sm">
            <div className="flex items-center gap-2">
              <ToolStatusIcon result={result} />
              <span className="font-medium text-[var(--text)]">{result.name}</span>
            </div>
            {result.error_message && <p className="mt-1 text-xs text-[#ef4444]">{result.error_message}</p>}
            {result.reason && !result.error_message && <p className="mt-0.5 text-xs text-[var(--muted)]">{result.reason}</p>}
          </li>
        ))}
      </ul>
    </div>
  );
}
