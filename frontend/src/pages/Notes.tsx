/**
 * Notes board.
 *
 * Displays agent investigation notes (and any human-authored notes) as a
 * threaded discussion feed: each note has a title, body, author tag, and a
 * comment thread that any teammate can reply on. Notes are stored on the
 * backend (`src/api/notes.py`) and broadcast over WebSocket when added so
 * everyone watching sees them in near-real-time.
 *
 * In a real run, agents publish notes via:
 *   await self.broadcast(content, metadata={"note": True, "title": "..."})
 * which the bus auto-promotes into a board entry. The user can also publish
 * manual notes from this page via the "+ New note" composer.
 */
import { useEffect, useMemo, useState } from 'react';
import { StickyNote, Plus, MessageSquare, Trash2, X, Send } from 'lucide-react';
import { api, type Note, type NoteComment } from '../api/client';

const AGENT_VISUALS: Record<string, { color: string; label: string; icon: string }> = {
  product:     { color: '#bc8cff', label: 'Product',   icon: '📋' },
  pm:          { color: '#58a6ff', label: 'PM',        icon: '📊' },
  architect:   { color: '#f0883e', label: 'Architect', icon: '🏗️' },
  frontend:    { color: '#3fb950', label: 'Frontend',  icon: '🎨' },
  backend:     { color: '#d29922', label: 'Backend',   icon: '⚙️' },
  qa:          { color: '#f85149', label: 'QA',        icon: '🧪' },
  devops:      { color: '#56d4dd', label: 'DevOps',    icon: '🚀' },
  code_review: { color: '#a371f7', label: 'Reviewer',  icon: '👁️' },
  user:        { color: '#8b949e', label: 'You',       icon: '🧑' },
  system:      { color: '#8b949e', label: 'System',    icon: '⚙️' },
};

function vis(author: string) {
  return AGENT_VISUALS[author] || { color: '#8b949e', label: author, icon: '🤖' };
}

function timeAgo(epoch: number): string {
  const seconds = Math.max(1, Math.floor(Date.now() / 1000 - epoch));
  if (seconds < 60) return `${seconds}s ago`;
  const minutes = Math.floor(seconds / 60);
  if (minutes < 60) return `${minutes}m ago`;
  const hours = Math.floor(minutes / 60);
  if (hours < 24) return `${hours}h ago`;
  return `${Math.floor(hours / 24)}d ago`;
}

export default function NotesPage() {
  const [notes, setNotes] = useState<Note[]>([]);
  const [filter, setFilter] = useState('');
  const [composerOpen, setComposerOpen] = useState(false);
  const [composerTitle, setComposerTitle] = useState('');
  const [composerBody, setComposerBody] = useState('');
  const [composerTicket, setComposerTicket] = useState('');

  // Load + auto-refresh every 5s while on this page
  const refresh = async () => {
    try {
      setNotes(await api.listNotes());
    } catch { /* ignore */ }
  };

  useEffect(() => {
    refresh();
    const t = setInterval(refresh, 5000);
    return () => clearInterval(t);
  }, []);

  const filtered = useMemo(() => {
    if (!filter) return notes;
    const q = filter.toLowerCase();
    return notes.filter(n =>
      n.title.toLowerCase().includes(q) ||
      n.body.toLowerCase().includes(q) ||
      n.author.toLowerCase().includes(q) ||
      n.ticket_key.toLowerCase().includes(q),
    );
  }, [notes, filter]);

  const submitNote = async () => {
    if (!composerTitle.trim()) return;
    try {
      await api.addNote({
        author: 'user',
        title: composerTitle,
        body: composerBody,
        ticket_key: composerTicket,
      });
      setComposerTitle('');
      setComposerBody('');
      setComposerTicket('');
      setComposerOpen(false);
      refresh();
    } catch { /* ignore */ }
  };

  return (
    <>
      <div className="page-header">
        <h2><StickyNote size={24} style={{ verticalAlign: 'middle', marginRight: 8 }} />Notes</h2>
        <p>Investigation notes and inter-agent discussion threads</p>
      </div>

      <div className="notes-toolbar">
        <input
          className="form-input"
          placeholder="Filter notes by title, body, author or ticket key..."
          value={filter}
          onChange={e => setFilter(e.target.value)}
          style={{ flex: 1, maxWidth: 480 }}
        />
        <button className="btn btn-primary" onClick={() => setComposerOpen(true)}>
          <Plus size={14} /> New note
        </button>
      </div>

      <div className="notes-list">
        {filtered.length === 0 ? (
          <div className="empty-state">
            <h3>No notes yet</h3>
            <p>
              Agents publish investigation notes and findings as they work. You can also
              add manual notes (e.g. context, decisions, follow-ups) using the
              <strong> New note</strong> button above.
            </p>
          </div>
        ) : (
          filtered.map(n => <NoteCard key={n.id} note={n} onUpdate={refresh} />)
        )}
      </div>

      {composerOpen && (
        <div className="connector-modal-overlay" onClick={e => { if (e.target === e.currentTarget) setComposerOpen(false); }}>
          <div className="connector-modal">
            <div className="connector-modal-header">
              <h3 style={{ margin: 0, fontSize: 16 }}>New note</h3>
              <button className="chat-popup-btn" onClick={() => setComposerOpen(false)}><X size={16} /></button>
            </div>
            <div className="connector-modal-body">
              <div className="form-group">
                <label>Title</label>
                <input
                  className="form-input"
                  placeholder="Brief summary..."
                  value={composerTitle}
                  onChange={e => setComposerTitle(e.target.value)}
                  autoFocus
                />
              </div>
              <div className="form-group">
                <label>Body (optional)</label>
                <textarea
                  className="form-input"
                  placeholder="Investigation findings, decisions, follow-ups..."
                  value={composerBody}
                  onChange={e => setComposerBody(e.target.value)}
                  rows={6}
                  style={{ resize: 'vertical', fontFamily: 'inherit' }}
                />
              </div>
              <div className="form-group">
                <label>Ticket key (optional)</label>
                <input
                  className="form-input"
                  placeholder="e.g. QA-35808"
                  value={composerTicket}
                  onChange={e => setComposerTicket(e.target.value)}
                />
              </div>
            </div>
            <div className="connector-modal-footer">
              <button className="btn btn-outline" onClick={() => setComposerOpen(false)}>Cancel</button>
              <button className="btn btn-primary" onClick={submitNote} disabled={!composerTitle.trim()}>
                Publish note
              </button>
            </div>
          </div>
        </div>
      )}
    </>
  );
}

function NoteCard({ note, onUpdate }: { note: Note; onUpdate: () => void }) {
  const v = vis(note.author);
  const [showComments, setShowComments] = useState(note.comments.length > 0);
  const [commentDraft, setCommentDraft] = useState('');
  const [commentAuthor, setCommentAuthor] = useState('user');

  const submitComment = async () => {
    if (!commentDraft.trim()) return;
    try {
      await api.addNoteComment(note.id, { author: commentAuthor, body: commentDraft });
      setCommentDraft('');
      onUpdate();
    } catch { /* ignore */ }
  };

  const handleDelete = async () => {
    if (!confirm(`Delete note "${note.title}"?`)) return;
    try {
      await api.deleteNote(note.id);
      onUpdate();
    } catch { /* ignore */ }
  };

  return (
    <article className="note-card" style={{ borderLeftColor: v.color }}>
      <header className="note-card-header">
        <span className="note-card-avatar" style={{ background: v.color + '22', color: v.color }}>{v.icon}</span>
        <div className="note-card-meta">
          <div className="note-card-author" style={{ color: v.color }}>{v.label}</div>
          <div className="note-card-sub">
            {timeAgo(note.created_at)}
            {note.ticket_key && (
              <span className="note-card-tag note-card-tag--ticket">{note.ticket_key}</span>
            )}
            {note.tags?.map(t => (
              <span key={t} className="note-card-tag">{t}</span>
            ))}
          </div>
        </div>
        <button className="note-card-delete" onClick={handleDelete} title="Delete">
          <Trash2 size={14} />
        </button>
      </header>

      <h3 className="note-card-title">{note.title}</h3>
      {note.body && <div className="note-card-body">{note.body}</div>}

      <button
        type="button"
        className="note-card-comments-toggle"
        onClick={() => setShowComments(s => !s)}
      >
        <MessageSquare size={12} />
        {note.comments.length} comment{note.comments.length === 1 ? '' : 's'}
      </button>

      {showComments && (
        <div className="note-card-comments">
          {note.comments.map(c => <CommentRow key={c.id} c={c} />)}
          <div className="note-comment-composer">
            <select
              className="settings-select"
              value={commentAuthor}
              onChange={e => setCommentAuthor(e.target.value)}
              style={{ minWidth: 120 }}
              title="Comment as..."
            >
              <option value="user">You</option>
              {Object.entries(AGENT_VISUALS).filter(([id]) => !['user', 'system'].includes(id)).map(([id, v]) => (
                <option key={id} value={id}>{v.label}</option>
              ))}
            </select>
            <input
              className="form-input"
              placeholder="Reply to this note..."
              value={commentDraft}
              onChange={e => setCommentDraft(e.target.value)}
              onKeyDown={e => e.key === 'Enter' && !e.shiftKey && (e.preventDefault(), submitComment())}
              style={{ flex: 1 }}
            />
            <button className="btn btn-primary" onClick={submitComment} disabled={!commentDraft.trim()}>
              <Send size={12} />
            </button>
          </div>
        </div>
      )}
    </article>
  );
}

function CommentRow({ c }: { c: NoteComment }) {
  const v = vis(c.author);
  return (
    <div className="note-comment">
      <span className="note-comment-avatar" style={{ background: v.color + '22', color: v.color }}>{v.icon}</span>
      <div className="note-comment-bubble">
        <div className="note-comment-author" style={{ color: v.color }}>
          {v.label}
          <span className="note-comment-time">{timeAgo(c.created_at)}</span>
        </div>
        <div className="note-comment-body">{c.body}</div>
      </div>
    </div>
  );
}
