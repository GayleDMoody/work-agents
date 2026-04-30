/**
 * Full-screen viewer for what the agents produced during a pipeline run.
 *
 * Two-pane layout:
 *   - Left: list of artifacts (one per agent) grouped by type (code / plan /
 *     design / review / analysis), with file counts.
 *   - Right: viewer for the selected artifact. Code artifacts render as a
 *     file tree + monospace-syntax content with action badges (create /
 *     modify / delete). JSON artifacts render the structured output. Other
 *     artifacts fall back to a plain-text view of `raw`.
 *
 * Designed to be opened from the Dashboard or Pipeline Detail page so the
 * user can see exactly what the agents wrote — closest analogue is the
 * Codex / Claude Code "diff view" feel.
 */
import { useEffect, useMemo, useState } from 'react';
import { X, FileText, Code, ListChecks, Eye, FilePlus2, FilePenLine, FileMinus2, Search, FileJson } from 'lucide-react';
import type { Artifact, ArtifactFile, Pipeline } from '../types';

interface Props {
  pipeline: Pipeline;
  onClose: () => void;
}

const AGENT_VISUALS: Record<string, { color: string; label: string; icon: string }> = {
  product:     { color: '#bc8cff', label: 'Product',   icon: '📋' },
  pm:          { color: '#58a6ff', label: 'PM',        icon: '📊' },
  architect:   { color: '#f0883e', label: 'Architect', icon: '🏗️' },
  frontend:    { color: '#3fb950', label: 'Frontend',  icon: '🎨' },
  backend:     { color: '#d29922', label: 'Backend',   icon: '⚙️' },
  qa:          { color: '#f85149', label: 'QA',        icon: '🧪' },
  devops:      { color: '#56d4dd', label: 'DevOps',    icon: '🚀' },
  code_review: { color: '#a371f7', label: 'Reviewer',  icon: '👁️' },
};

function typeIcon(t: string) {
  switch (t) {
    case 'code':     return <Code size={14} />;
    case 'plan':     return <ListChecks size={14} />;
    case 'design':   return <FileJson size={14} />;
    case 'review':   return <Eye size={14} />;
    default:         return <FileText size={14} />;
  }
}

function actionBadge(action: string) {
  switch (action) {
    case 'create': return { color: '#3fb950', icon: <FilePlus2 size={12} />,  label: 'create' };
    case 'modify': return { color: '#d29922', icon: <FilePenLine size={12} />, label: 'modify' };
    case 'delete': return { color: '#f85149', icon: <FileMinus2 size={12} />,  label: 'delete' };
    default:       return { color: '#8b949e', icon: <FileText size={12} />,    label: action || '—' };
  }
}

export default function ArtifactViewer({ pipeline, onClose }: Props) {
  const artifacts = pipeline.artifacts || [];
  const [selectedId, setSelectedId] = useState<string | null>(artifacts[0]?.id ?? null);
  const [selectedFilePath, setSelectedFilePath] = useState<string | null>(null);
  const [search, setSearch] = useState('');

  const selected: Artifact | undefined = artifacts.find(a => a.id === selectedId);

  // When the selected artifact changes, default to its first file (if any)
  useEffect(() => {
    if (!selected) {
      setSelectedFilePath(null);
      return;
    }
    setSelectedFilePath(selected.files?.[0]?.path ?? null);
  }, [selectedId]);  // eslint-disable-line react-hooks/exhaustive-deps

  const file: ArtifactFile | undefined = useMemo(
    () => selected?.files?.find(f => f.path === selectedFilePath),
    [selected, selectedFilePath],
  );

  // Group artifacts by their type for the left rail
  const grouped = useMemo(() => {
    const out: Record<string, Artifact[]> = {};
    for (const a of artifacts) {
      const key = a.artifact_type || 'analysis';
      (out[key] ||= []).push(a);
    }
    return out;
  }, [artifacts]);

  // Esc to close
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => { if (e.key === 'Escape') onClose(); };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [onClose]);

  const filteredFiles = (selected?.files || []).filter(
    f => !search || f.path.toLowerCase().includes(search.toLowerCase()),
  );

  return (
    <div className="artifact-viewer-overlay" onClick={e => { if (e.target === e.currentTarget) onClose(); }}>
      <div className="artifact-viewer">
        <div className="artifact-viewer-header">
          <div>
            <div className="artifact-viewer-title">Artifacts — {pipeline.ticket_key}</div>
            <div className="artifact-viewer-sub">
              {artifacts.length} artifact{artifacts.length === 1 ? '' : 's'} · {pipeline.status} · ${(pipeline.total_cost ?? 0).toFixed(2)}
            </div>
          </div>
          <button className="artifact-viewer-close" onClick={onClose} aria-label="Close">
            <X size={18} />
          </button>
        </div>

        <div className="artifact-viewer-body">
          {/* Left rail — artifact list grouped by type */}
          <div className="artifact-rail">
            {Object.entries(grouped).map(([type, list]) => (
              <div key={type} className="artifact-rail-group">
                <div className="artifact-rail-group-title">{type}</div>
                {list.map(a => {
                  const vis = AGENT_VISUALS[a.agent_id] || { color: '#8b949e', label: a.agent_id, icon: '🤖' };
                  const fileCount = a.files?.length ?? 0;
                  return (
                    <button
                      key={a.id}
                      type="button"
                      className={`artifact-rail-item ${selectedId === a.id ? 'active' : ''}`}
                      onClick={() => setSelectedId(a.id)}
                      style={{ borderLeftColor: vis.color }}
                    >
                      <span className="artifact-rail-icon">{typeIcon(a.artifact_type)}</span>
                      <span className="artifact-rail-text">
                        <span className="artifact-rail-agent" style={{ color: vis.color }}>{vis.label}</span>
                        <span className="artifact-rail-name">{a.name || '(no description)'}</span>
                      </span>
                      {fileCount > 0 && (
                        <span className="artifact-rail-count">{fileCount}</span>
                      )}
                    </button>
                  );
                })}
              </div>
            ))}
            {artifacts.length === 0 && (
              <div className="artifact-rail-empty">No artifacts produced yet.</div>
            )}
          </div>

          {/* Right pane — viewer */}
          <div className="artifact-pane">
            {!selected ? (
              <div className="artifact-empty-state">
                <FileText size={32} style={{ opacity: 0.3 }} />
                <div>Select an artifact from the left to view it</div>
              </div>
            ) : (
              <ArtifactBody
                artifact={selected}
                file={file}
                filteredFiles={filteredFiles}
                allFiles={selected.files || []}
                selectedFilePath={selectedFilePath}
                onSelectFile={setSelectedFilePath}
                search={search}
                onSearchChange={setSearch}
              />
            )}
          </div>
        </div>
      </div>
    </div>
  );
}

function ArtifactBody({
  artifact, file, filteredFiles, allFiles, selectedFilePath, onSelectFile, search, onSearchChange,
}: {
  artifact: Artifact;
  file: ArtifactFile | undefined;
  filteredFiles: ArtifactFile[];
  allFiles: ArtifactFile[];
  selectedFilePath: string | null;
  onSelectFile: (path: string) => void;
  search: string;
  onSearchChange: (s: string) => void;
}) {
  const vis = AGENT_VISUALS[artifact.agent_id] || { color: '#8b949e', label: artifact.agent_id, icon: '🤖' };
  const hasFiles = (artifact.files?.length ?? 0) > 0;

  return (
    <>
      <div className="artifact-pane-header">
        <span className="artifact-pane-icon" style={{ background: vis.color + '22', color: vis.color }}>{vis.icon}</span>
        <div style={{ flex: 1, minWidth: 0 }}>
          <div className="artifact-pane-name">{artifact.name || vis.label}</div>
          <div className="artifact-pane-meta">{vis.label} · {artifact.artifact_type}{hasFiles ? ` · ${allFiles.length} file${allFiles.length === 1 ? '' : 's'}` : ''}</div>
        </div>
      </div>

      {hasFiles ? (
        <div className="artifact-code-layout">
          <div className="artifact-tree">
            <div className="artifact-tree-search">
              <Search size={12} />
              <input
                placeholder="Filter files..."
                value={search}
                onChange={e => onSearchChange(e.target.value)}
              />
            </div>
            <div className="artifact-tree-list">
              {filteredFiles.map(f => {
                const ab = actionBadge(f.action);
                return (
                  <button
                    key={f.path}
                    type="button"
                    className={`artifact-tree-item ${selectedFilePath === f.path ? 'active' : ''}`}
                    onClick={() => onSelectFile(f.path)}
                  >
                    <span style={{ color: ab.color }}>{ab.icon}</span>
                    <span className="artifact-tree-path">{f.path}</span>
                  </button>
                );
              })}
              {filteredFiles.length === 0 && (
                <div className="artifact-tree-empty">No matching files.</div>
              )}
            </div>
          </div>

          <div className="artifact-code">
            {file ? (
              <FileView file={file} />
            ) : (
              <div className="artifact-empty-state">
                <Code size={28} style={{ opacity: 0.3 }} />
                <div>Select a file</div>
              </div>
            )}
          </div>
        </div>
      ) : artifact.json_dict ? (
        <div className="artifact-json">
          <pre>{JSON.stringify(artifact.json_dict, null, 2)}</pre>
        </div>
      ) : (
        <div className="artifact-text">
          <pre>{artifact.raw || '(no content)'}</pre>
        </div>
      )}
    </>
  );
}

function FileView({ file }: { file: ArtifactFile }) {
  const ab = actionBadge(file.action);
  const lines = (file.content || '').split('\n');

  // Render lines with a "+" prefix for create/modify (visual diff feel) and "-" for delete.
  const sigil = file.action === 'delete' ? '-' : '+';
  const sigilColor = file.action === 'delete' ? '#f85149' : '#3fb950';
  const lineBg     = file.action === 'delete' ? 'rgba(248,81,73,0.05)' : 'rgba(63,185,80,0.04)';

  return (
    <>
      <div className="file-header">
        <span className="file-action" style={{ color: ab.color }}>{ab.icon} {ab.label}</span>
        <span className="file-path">{file.path}</span>
        <span className="file-stats">{lines.length} line{lines.length === 1 ? '' : 's'}</span>
      </div>
      {file.description && (
        <div className="file-desc">{file.description}</div>
      )}
      <div className="file-code" style={{ background: lineBg }}>
        {lines.map((line, i) => (
          <div key={i} className="file-line">
            <span className="file-line-no">{i + 1}</span>
            <span className="file-line-sigil" style={{ color: sigilColor }}>{sigil}</span>
            <span className="file-line-content">{line || ' '}</span>
          </div>
        ))}
      </div>
    </>
  );
}
