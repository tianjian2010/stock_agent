import { useState } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { Database, FileStack, FileText, RefreshCw, Upload } from 'lucide-react';

import SidebarChatHistory from '@/features/history/SidebarChatHistory';
import { api } from '@/lib/api/client';
import type { UploadDocumentsResponse } from '@/types';

function formatFileSize(size: number) {
  if (size < 1024) return `${size} B`;
  if (size < 1024 * 1024) return `${(size / 1024).toFixed(1)} KB`;
  return `${(size / (1024 * 1024)).toFixed(1)} MB`;
}

export default function DocumentsPage() {
  const qc = useQueryClient();
  const [files, setFiles] = useState<File[]>([]);
  const [overwrite, setOverwrite] = useState(false);
  const [lastUpload, setLastUpload] = useState<UploadDocumentsResponse | null>(null);

  const { data: stats, isLoading: statsLoading } = useQuery({
    queryKey: ['adminIndex'],
    queryFn: api.getAdminIndex,
  });

  const { data: documents = [], isLoading: docsLoading } = useQuery({
    queryKey: ['adminDocuments'],
    queryFn: () => api.getAdminDocuments(),
  });

  const uploadMutation = useMutation({
    mutationFn: () => api.uploadDocuments(files, overwrite),
    onSuccess: (result) => {
      setLastUpload(result);
      setFiles([]);
      qc.invalidateQueries({ queryKey: ['adminIndex'] });
      qc.invalidateQueries({ queryKey: ['adminDocuments'] });
      qc.invalidateQueries({ queryKey: ['stats'] });
    },
  });

  const reindexMutation = useMutation({
    mutationFn: api.reindexDocumentsSync,
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['adminIndex'] });
      qc.invalidateQueries({ queryKey: ['adminDocuments'] });
      qc.invalidateQueries({ queryKey: ['stats'] });
    },
  });

  return (
    <div className="relative flex min-h-screen overflow-hidden">
      <SidebarChatHistory />

      <main className="flex min-w-0 flex-1 flex-col">
        <header className="border-b border-[var(--border)] bg-[var(--surface)] px-5 py-5 shadow-[0_1px_0_rgba(255,255,255,0.45)] backdrop-blur-xl md:px-8">
          <p className="text-[11px] font-semibold uppercase tracking-[0.28em] text-[var(--muted)]">
            Document Control
          </p>
          <div className="mt-2 flex flex-col gap-3 md:flex-row md:items-end md:justify-between">
            <div>
              <h1 className="text-2xl font-semibold text-[var(--text)]">资料管理</h1>
              <p className="mt-1 max-w-2xl text-sm text-[var(--muted)]">
                上传到 `stock_docs` 的新文件会立即执行增量入库，系统启动时也会自动补齐未完成矢量化的资料。
              </p>
            </div>
            <button
              type="button"
              onClick={() => reindexMutation.mutate()}
              disabled={reindexMutation.isPending}
              className="inline-flex items-center justify-center gap-2 rounded-2xl border border-[var(--border)] bg-white/80 px-4 py-2.5 text-sm font-medium text-[var(--text)] shadow-[var(--shadow-soft)] transition-colors hover:border-[var(--border-strong)] disabled:cursor-not-allowed disabled:opacity-60"
            >
              <RefreshCw size={16} className={reindexMutation.isPending ? 'animate-spin' : ''} />
              手动同步索引
            </button>
          </div>
        </header>

        <div className="flex-1 overflow-y-auto px-5 py-6 md:px-8">
          <section className="grid gap-4 lg:grid-cols-[1.1fr_0.9fr]">
            <div className="rounded-[28px] border border-[var(--border)] bg-[rgba(255,255,255,0.72)] p-5 shadow-[var(--shadow-soft)]">
              <div className="flex items-center gap-2 text-sm font-medium text-[var(--text)]">
                <Upload size={16} className="text-[var(--accent-2)]" />
                上传新增资料
              </div>
              <p className="mt-2 text-sm text-[var(--muted)]">
                支持 `txt`、`docx`、`pdf`、`xlsx`、`xls`、`csv` 以及已转写音频。
              </p>

              <label className="mt-5 flex cursor-pointer flex-col items-center justify-center rounded-[24px] border border-dashed border-[rgba(56,87,106,0.28)] bg-[linear-gradient(135deg,rgba(255,255,255,0.84),rgba(233,225,211,0.84))] px-6 py-10 text-center transition-colors hover:border-[rgba(56,87,106,0.42)]">
                <Upload size={22} className="mb-3 text-[var(--accent-2)]" />
                <span className="text-sm font-medium text-[var(--text)]">选择一个或多个新增文件</span>
                <span className="mt-1 text-xs text-[var(--muted)]">
                  上传后会复制到本地资料目录，并立即执行增量矢量化。
                </span>
                <input
                  type="file"
                  multiple
                  className="hidden"
                  onChange={(event) => setFiles(Array.from(event.target.files || []))}
                />
              </label>

              {files.length > 0 && (
                <div className="mt-4 rounded-2xl bg-[#f6f0e5] px-4 py-3 text-sm text-[var(--text)]">
                  已选择 {files.length} 个文件：{files.slice(0, 3).map((file) => file.name).join('、')}
                  {files.length > 3 ? ' 等' : ''}
                </div>
              )}

              <div className="mt-4 flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
                <label className="inline-flex items-center gap-2 text-sm text-[var(--muted)]">
                  <input
                    type="checkbox"
                    checked={overwrite}
                    onChange={(event) => setOverwrite(event.target.checked)}
                    className="h-4 w-4 rounded border-[var(--border)]"
                  />
                  同名文件允许覆盖
                </label>
                <button
                  type="button"
                  onClick={() => uploadMutation.mutate()}
                  disabled={files.length === 0 || uploadMutation.isPending}
                  className="inline-flex items-center justify-center gap-2 rounded-2xl bg-[#243746] px-4 py-2.5 text-sm font-medium text-white shadow-[var(--shadow-soft)] transition-colors hover:bg-[#314c60] disabled:cursor-not-allowed disabled:opacity-60"
                >
                  <Upload size={16} />
                  {uploadMutation.isPending ? '上传中...' : '上传并入库'}
                </button>
              </div>

              {lastUpload && (
                <div className="mt-5 rounded-2xl border border-[var(--border)] bg-white/70 p-4 text-sm">
                  <p className="font-medium text-[var(--text)]">
                    本次处理：成功 {lastUpload.saved.length} 个，跳过 {lastUpload.skipped.length} 个
                  </p>
                  <p className="mt-2 text-[var(--muted)]">
                    索引结果：更新 {lastUpload.index_result.updated_files} 个文件，当前共{' '}
                    {lastUpload.index_result.document_count} 份资料。
                  </p>
                </div>
              )}

              {uploadMutation.isError && (
                <div className="mt-5 rounded-2xl border border-[#f0c8bf] bg-[#fff0ec] px-4 py-3 text-sm text-[#b23c2f]">
                  {(uploadMutation.error as Error).message}
                </div>
              )}
            </div>

            <div className="grid gap-4">
              <div className="rounded-[28px] border border-[var(--border)] bg-[rgba(255,253,248,0.82)] p-5 shadow-[var(--shadow-soft)]">
                <div className="flex items-center gap-2 text-sm font-medium text-[var(--text)]">
                  <Database size={16} className="text-[var(--accent)]" />
                  索引状态
                </div>
                <div className="mt-4 grid gap-3 sm:grid-cols-2">
                  <div className="rounded-2xl bg-[#f6f0e5] px-4 py-3">
                    <p className="text-xs uppercase tracking-[0.18em] text-[var(--muted)]">Documents</p>
                    <p className="mt-2 text-2xl font-semibold text-[var(--text)]">
                      {statsLoading ? '-' : stats?.document_count ?? 0}
                    </p>
                  </div>
                  <div className="rounded-2xl bg-[#edf2f4] px-4 py-3">
                    <p className="text-xs uppercase tracking-[0.18em] text-[var(--muted)]">Chunks</p>
                    <p className="mt-2 text-2xl font-semibold text-[var(--text)]">
                      {statsLoading ? '-' : stats?.chunk_count ?? 0}
                    </p>
                  </div>
                </div>
                <div className="mt-4 flex items-center justify-between rounded-2xl border border-[var(--border)] bg-white/70 px-4 py-3 text-sm">
                  <span className="text-[var(--muted)]">向量库状态</span>
                  <span className="font-medium text-[var(--text)]">
                    {stats?.vector_ready ? '已就绪' : '未就绪'}
                  </span>
                </div>
                {reindexMutation.isSuccess && (
                  <p className="mt-3 text-sm text-[var(--muted)]">
                    最近一次手动同步已完成，新增/变更文件已重新检查。
                  </p>
                )}
              </div>

              <div className="rounded-[28px] border border-[var(--border)] bg-[rgba(255,255,255,0.72)] p-5 shadow-[var(--shadow-soft)]">
                <div className="flex items-center gap-2 text-sm font-medium text-[var(--text)]">
                  <FileStack size={16} className="text-[var(--accent-2)]" />
                  处理规则
                </div>
                <div className="mt-4 space-y-3 text-sm text-[var(--muted)]">
                  <p>1. 服务启动时会扫描 `stock_docs`，把未矢量化、已修改或缺失的文件补入向量库。</p>
                  <p>2. 通过这里上传的新文件会先落盘，再立即执行增量入库。</p>
                  <p>3. 后台定时任务仍会继续巡检，避免漏掉手工拷贝进目录的新文件。</p>
                </div>
              </div>
            </div>
          </section>

          <section className="mt-6 rounded-[28px] border border-[var(--border)] bg-[rgba(255,253,248,0.8)] p-5 shadow-[var(--shadow-soft)]">
            <div className="flex items-center gap-2 text-sm font-medium text-[var(--text)]">
              <FileText size={16} className="text-[var(--accent)]" />
              已纳入资料
            </div>

            {docsLoading ? (
              <p className="mt-4 text-sm text-[var(--muted)]">正在读取文档列表...</p>
            ) : documents.length === 0 ? (
              <p className="mt-4 text-sm text-[var(--muted)]">当前还没有可管理的资料。</p>
            ) : (
              <div className="mt-4 overflow-hidden rounded-2xl border border-[var(--border)]">
                <div className="grid grid-cols-[minmax(0,2.2fr)_minmax(0,1.2fr)_120px_100px] gap-3 bg-[#f6f0e5] px-4 py-3 text-xs font-semibold uppercase tracking-[0.18em] text-[var(--muted)]">
                  <span>文件名</span>
                  <span>主题</span>
                  <span>日期</span>
                  <span>大小</span>
                </div>
                <div className="divide-y divide-[var(--border)] bg-white/75">
                  {documents.map((document) => (
                    <div
                      key={`${document.filename}-${document.source}`}
                      className="grid grid-cols-[minmax(0,2.2fr)_minmax(0,1.2fr)_120px_100px] gap-3 px-4 py-3 text-sm"
                    >
                      <span className="truncate text-[var(--text)]">{document.filename}</span>
                      <span className="truncate text-[var(--muted)]">{document.topic}</span>
                      <span className="text-[var(--muted)]">{document.published_at || '-'}</span>
                      <span className="text-[var(--muted)]">{formatFileSize(document.size)}</span>
                    </div>
                  ))}
                </div>
              </div>
            )}
          </section>
        </div>
      </main>
    </div>
  );
}
