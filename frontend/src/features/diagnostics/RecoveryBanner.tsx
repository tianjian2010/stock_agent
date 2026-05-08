import { AlertTriangle, RotateCcw } from 'lucide-react';

interface RecoveryData {
  recovered?: boolean;
  degraded?: boolean;
  recovery_action?: string;
  error_message?: string;
  [key: string]: unknown;
}

interface RecoveryBannerProps {
  recovery?: RecoveryData;
}

export function RecoveryBanner({ recovery }: RecoveryBannerProps) {
  if (!recovery || Object.keys(recovery).length === 0) return null;

  const hasError = !!recovery.error_message;
  const isDegraded = !!recovery.degraded;
  const hasRecovery = !!recovery.recovery_action;

  if (!hasError && !isDegraded && !hasRecovery) return null;

  return (
    <div
      className={`mx-4 mb-4 rounded-2xl border px-4 py-3 text-sm shadow-[var(--shadow-soft)] ${
        hasError
          ? 'border-[#f0c8bf] bg-[#fff0ec]'
          : isDegraded
          ? 'border-[#f3d2a8] bg-[#fff7eb]'
          : 'border-[#cfe7da] bg-[#f2fbf6]'
      }`}
    >
      <div className="flex items-start gap-3">
        {hasError ? (
          <AlertTriangle size={16} className="mt-0.5 shrink-0 text-[#ef4444]" />
        ) : (
          <RotateCcw size={16} className="mt-0.5 shrink-0 text-[#10b981]" />
        )}
        <div className="flex-1">
          {hasError && <p className="font-medium text-[#dc2626]">执行异常</p>}
          {isDegraded && !hasError && <p className="font-medium text-[#d97706]">降级运行</p>}
          {hasRecovery && !hasError && <p className="font-medium text-[#059669]">已自动恢复</p>}
          {recovery.error_message && <p className="mt-1 text-xs text-[#991b1b]">{recovery.error_message}</p>}
          {recovery.recovery_action && (
            <p className="mt-1 text-xs text-[#065f46]">恢复措施: {recovery.recovery_action}</p>
          )}
        </div>
      </div>
    </div>
  );
}
