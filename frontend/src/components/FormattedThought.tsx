/**
 * Smart renderer for an agent thought's content.
 *
 * Detects shape and renders accordingly:
 *   - Valid JSON     → collapsible tree view with key/value styling
 *   - Fenced code    → code block with monospace + line numbers
 *   - "[role] body"  → split header (role pill) + body
 *   - Plain text     → paragraphs + clickable URLs, with truncation
 *
 * The goal is to turn the firehose of raw model output into something a
 * human watching the demo can scan in <2 seconds per panel.
 */
import { useMemo, useState } from 'react';
import { ChevronRight, ChevronDown } from 'lucide-react';

interface Props {
  content: string;
  /** Initial truncation threshold in characters; user can expand past it. */
  maxChars?: number;
}

export default function FormattedThought({ content, maxChars = 600 }: Props) {
  const [expanded, setExpanded] = useState(false);

  // Try to peel a JSON value out of the content. Models often wrap the JSON
  // in markdown fences or prefix it with explanatory text — find the first
  // `{...}` or `[...]` and parse from there.
  const parsed = useMemo(() => tryParseJson(content), [content]);

  if (parsed.kind === 'json') {
    return (
      <div className="ft-root ft-json">
        {parsed.preamble && <div className="ft-pre">{parsed.preamble}</div>}
        <JsonProse value={parsed.value} />
        <details className="ft-details">
          <summary className="ft-details-summary">Show full structure</summary>
          <JsonNode value={parsed.value} keyName={null} depth={0} />
        </details>
      </div>
    );
  }

  if (parsed.kind === 'code') {
    return (
      <div className="ft-root ft-code-wrap">
        {parsed.preamble && <div className="ft-pre">{parsed.preamble}</div>}
        {parsed.blocks.map((b, i) => (
          <CodeBlock key={i} lang={b.lang} body={b.body} />
        ))}
      </div>
    );
  }

  // Plain text path
  const text = (content || '').trim();
  const isLong = text.length > maxChars;
  const display = expanded || !isLong ? text : text.slice(0, maxChars) + '…';
  return (
    <div className="ft-root ft-text">
      <FormattedText text={display} />
      {isLong && (
        <button type="button" className="ft-toggle" onClick={() => setExpanded(v => !v)}>
          {expanded ? 'Show less' : 'Show more'}
        </button>
      )}
    </div>
  );
}

// ---------------------------------------------------------------------------
// JSON detection / parsing
// ---------------------------------------------------------------------------

type ParseResult =
  | { kind: 'json'; value: unknown; preamble: string }
  | { kind: 'code'; blocks: { lang: string; body: string }[]; preamble: string }
  | { kind: 'text' };

function tryParseJson(s: string): ParseResult {
  if (!s) return { kind: 'text' };
  const trimmed = s.trim();

  // Fenced code blocks first — common in agent responses. Even an UNCLOSED
  // fence (truncated content) is treated as a JSON candidate.
  const fenced = extractFencedBlocks(trimmed);
  const fencePrefix = trimmed.match(/^```(json)?\s*\n/i);
  if (fenced.blocks.length > 0 || fencePrefix) {
    // Try to parse the first block as JSON (even if truncated)
    const body = fenced.blocks[0]?.body
      ?? trimmed.replace(/^```(?:json)?\s*\n?/i, '').replace(/\n?```\s*$/i, '');
    const parsed = parseJsonForgiving(body);
    if (parsed !== undefined) {
      return { kind: 'json', value: parsed, preamble: fenced.preamble || '' };
    }
    if (fenced.blocks.length > 0) {
      return { kind: 'code', blocks: fenced.blocks, preamble: fenced.preamble };
    }
  }

  // No fences — try to find a JSON object/array by locating the first { or [
  const firstBrace = Math.min(...['{', '['].map(c => {
    const i = trimmed.indexOf(c);
    return i === -1 ? Infinity : i;
  }));
  if (firstBrace !== Infinity) {
    const candidate = trimmed.slice(firstBrace);
    const parsed = parseJsonForgiving(candidate);
    if (parsed !== undefined) {
      return { kind: 'json', value: parsed, preamble: trimmed.slice(0, firstBrace).trim() };
    }
  }

  return { kind: 'text' };
}

/** Parse JSON, trying progressively shorter prefixes if the input was
 *  truncated mid-object (we cap responses at 40 KB on the backend, which
 *  can still chop a long file array). Returns undefined if nothing parses. */
function parseJsonForgiving(s: string): unknown | undefined {
  const trimmed = s.trim();
  if (!trimmed) return undefined;
  // 1. Parse as-is
  try { return JSON.parse(trimmed); } catch { /* fall through */ }

  // 2. Walk the string and try every position where we just closed a top-
  //    level object/array
  let depth = 0, inStr = false, escape = false;
  const candidates: number[] = [];
  for (let i = 0; i < trimmed.length; i++) {
    const c = trimmed[i];
    if (escape) { escape = false; continue; }
    if (c === '\\') { escape = true; continue; }
    if (c === '"')  { inStr = !inStr; continue; }
    if (inStr) continue;
    if (c === '{' || c === '[') depth++;
    else if (c === '}' || c === ']') {
      depth--;
      if (depth === 0) candidates.unshift(i + 1);
    }
  }
  for (const end of candidates.slice(0, 6)) {
    try { return JSON.parse(trimmed.slice(0, end)); } catch { /* try next */ }
  }

  // 3. Repair: rebalance brackets / close strings / strip trailing commas
  //    so we can parse a syntactically-completed version of the truncated
  //    content. This is what salvages 30 KB+ multi-file responses where the
  //    truncation happened mid-`"content": "..."` of one file.
  const repaired = tryRepairJson(trimmed);
  if (repaired !== undefined) return repaired;

  return undefined;
}

/**
 * Attempt to make truncated JSON parseable by closing any unclosed string,
 * stripping a dangling escape, removing the last (likely incomplete) entry
 * of the deepest container, and appending the missing closing brackets.
 *
 * Doesn't try to be perfect — just good enough that JsonProse can render
 * the high-level shape (e.g. "Files (3): src/Foo.java, src/Bar.java, …")
 * even if the last entry is partial.
 */
function tryRepairJson(s: string): unknown | undefined {
  // Walk the string and track structural state
  let inStr = false;
  let escape = false;
  const stack: ('O' | 'A')[] = [];
  // Position of the start of the deepest currently-open container's last
  // entry (used to lop off a partial trailing entry on repair)
  for (let i = 0; i < s.length; i++) {
    const c = s[i];
    if (escape) { escape = false; continue; }
    if (c === '\\') { escape = true; continue; }
    if (c === '"')  { inStr = !inStr; continue; }
    if (inStr) continue;
    if (c === '{') stack.push('O');
    else if (c === '[') stack.push('A');
    else if (c === '}' || c === ']') stack.pop();
  }

  if (stack.length === 0 && !inStr) return undefined; // already balanced — first parse would have worked

  let repaired = s;

  // Strip dangling escape backslash
  if (escape) repaired = repaired.slice(0, -1);

  // Close an open string. If we were inside a string, the JSON parser will
  // be unhappy with whatever comes after — close it cleanly.
  if (inStr) repaired += '"';

  // Strip whitespace + trailing comma so we don't end on something like `,`
  repaired = repaired.replace(/[\s,]+$/, '');

  // If the deepest container was an array or object and we ended right after
  // a partial entry (no comma), JSON might be like `[ {a:1}, {a:2 ` — that's
  // fine, the next step closes brackets which produces `[{a:1}, {a:2}]`.
  // But if it was `[ {a:1}, {` (we just opened a new entry that has no
  // content), strip it.
  // Keep this simple — try the close first; on failure trim more.
  for (let attempt = 0; attempt < 4; attempt++) {
    let candidate = repaired;
    // Append missing closes
    for (let i = stack.length - 1; i >= 0; i--) {
      candidate += stack[i] === 'O' ? '}' : ']';
    }
    try { return JSON.parse(candidate); } catch { /* fall through */ }
    // Trim back to the previous comma/colon/open-bracket to drop the partial entry
    const cut = Math.max(
      repaired.lastIndexOf(','),
      repaired.lastIndexOf('['),
      repaired.lastIndexOf('{'),
    );
    if (cut <= 0) break;
    repaired = repaired.slice(0, cut).replace(/[\s,]+$/, '');
  }
  return undefined;
}

function looksLikeJson(s: string): boolean {
  if (!s) return false;
  const t = s.trim();
  return (t.startsWith('{') && t.endsWith('}')) || (t.startsWith('[') && t.endsWith(']'));
}

function extractFencedBlocks(s: string): { preamble: string; blocks: { lang: string; body: string }[] } {
  const re = /```([a-zA-Z0-9_-]*)\n([\s\S]*?)```/g;
  const blocks: { lang: string; body: string }[] = [];
  let preambleEnd = -1;
  let m: RegExpExecArray | null;
  while ((m = re.exec(s)) !== null) {
    if (preambleEnd === -1) preambleEnd = m.index;
    blocks.push({ lang: m[1] || '', body: m[2] });
  }
  return {
    preamble: preambleEnd === -1 ? '' : s.slice(0, preambleEnd).trim(),
    blocks,
  };
}

// ---------------------------------------------------------------------------
// Human-readable JSON prose
// ---------------------------------------------------------------------------

/**
 * Renders a JSON object as readable English by surfacing well-known fields
 * (summary, decision, rationale, files, acceptance_criteria, etc.) in a
 * natural format. This is the default view a user sees — the full JSON tree
 * is folded under a "Show full structure" disclosure below.
 */
function JsonProse({ value }: { value: unknown }) {
  if (value === null || value === undefined) return null;
  if (typeof value !== 'object') {
    return <div className="ft-prose-line">{String(value)}</div>;
  }
  if (Array.isArray(value)) {
    return (
      <div className="ft-prose">
        <div className="ft-prose-meta">List of {value.length} item{value.length === 1 ? '' : 's'}</div>
        {value.slice(0, 6).map((item, i) => (
          <ProseItem key={i} value={item} />
        ))}
        {value.length > 6 && <div className="ft-prose-more">+{value.length - 6} more…</div>}
      </div>
    );
  }
  const obj = value as Record<string, unknown>;

  // Surface the highest-priority readable fields first
  const rendered = new Set<string>();
  const pieces: React.ReactNode[] = [];

  // 1. The "main message" fields (one-line text)
  for (const k of ['plan_summary', 'summary', 'verdict', 'decision', 'rationale', 'reasoning', 'approach', 'description', 'response', 'message']) {
    const v = obj[k];
    if (typeof v === 'string' && v.trim()) {
      pieces.push(
        <div key={k} className="ft-prose-headline">
          <span className="ft-prose-label">{prettyLabel(k)}:</span> {v.trim()}
        </div>,
      );
      rendered.add(k);
    }
  }

  // 2. Multi-item "what's in this" arrays
  for (const k of ['acceptance_criteria', 'clarification_questions', 'edge_cases', 'risks', 'comments', 'security_issues',
                   'performance_concerns', 'questions_for_reviewer', 'followups', 'agents_needed', 'agents_not_needed',
                   'tags', 'patterns', 'dependencies', 'open_questions', 'breaking_changes',
                   'files', 'test_files', 'config_files', 'files_to_create', 'files_to_modify',
                   'env_vars_needed', 'migrations', 'api_changes', 'tests_added',
                   'steps', 'parallel_groups']) {
    const v = obj[k];
    if (Array.isArray(v) && v.length > 0) {
      pieces.push(
        <div key={k} className="ft-prose-section">
          <div className="ft-prose-label">{prettyLabel(k)} ({v.length})</div>
          <ul className="ft-prose-list">
            {v.slice(0, 8).map((item, i) => (
              <li key={i}><ProseItem value={item} compact /></li>
            ))}
            {v.length > 8 && <li className="ft-prose-more">+{v.length - 8} more…</li>}
          </ul>
        </div>,
      );
      rendered.add(k);
    }
  }

  // 3. Nested "result" / "metadata" / similar structured fields — fold them
  //    inside their own disclosures so the surface stays uncluttered.
  for (const k of Object.keys(obj)) {
    if (rendered.has(k)) continue;
    const v = obj[k];
    if (typeof v === 'string' && v.trim()) {
      pieces.push(
        <div key={k} className="ft-prose-line">
          <span className="ft-prose-label">{prettyLabel(k)}:</span> {clip(v, 240)}
        </div>,
      );
    } else if (typeof v === 'number' || typeof v === 'boolean') {
      pieces.push(
        <div key={k} className="ft-prose-line">
          <span className="ft-prose-label">{prettyLabel(k)}:</span> {String(v)}
        </div>,
      );
    } else if (v && typeof v === 'object' && !Array.isArray(v)) {
      // Render nested objects as "key: 3 fields" with a tooltip
      const childKeys = Object.keys(v as Record<string, unknown>);
      pieces.push(
        <div key={k} className="ft-prose-line ft-prose-line--nested">
          <span className="ft-prose-label">{prettyLabel(k)}:</span> <span className="ft-prose-meta">{childKeys.length} fields ({childKeys.slice(0, 3).join(', ')}{childKeys.length > 3 ? '…' : ''})</span>
        </div>,
      );
    } else if (Array.isArray(v)) {
      pieces.push(
        <div key={k} className="ft-prose-line">
          <span className="ft-prose-label">{prettyLabel(k)}:</span> <span className="ft-prose-meta">{v.length} item{v.length === 1 ? '' : 's'}</span>
        </div>,
      );
    }
  }

  return <div className="ft-prose">{pieces}</div>;
}

function ProseItem({ value, compact = false }: { value: unknown; compact?: boolean }) {
  if (value === null || value === undefined) return <span className="ft-null">none</span>;
  if (typeof value === 'string') return <span>{compact ? clip(value, 200) : value}</span>;
  if (typeof value === 'number' || typeof value === 'boolean') return <span>{String(value)}</span>;

  if (Array.isArray(value)) {
    return <span className="ft-prose-meta">[{value.length} item{value.length === 1 ? '' : 's'}]</span>;
  }
  const obj = value as Record<string, unknown>;

  // file-like { path, action, content }
  if (typeof obj.path === 'string' || typeof obj.filename === 'string') {
    const path = String(obj.path ?? obj.filename ?? '');
    const action = String(obj.action ?? obj.status ?? '');
    return (
      <span>
        {action && <span className={`ft-prose-pill ft-prose-pill--${action}`}>{action}</span>}
        <code>{path}</code>
        {typeof obj.description === 'string' && obj.description && <> — {clip(obj.description, 80)}</>}
      </span>
    );
  }

  // step-like { agent, task }
  if (typeof obj.agent === 'string' && typeof obj.task === 'string') {
    return <span><span className="ft-prose-pill">{obj.agent}</span>{clip(obj.task, 200)}</span>;
  }

  // comment-like { file, line, severity, comment }
  if (typeof obj.comment === 'string') {
    return (
      <span>
        {typeof obj.severity === 'string' && <span className={`ft-prose-pill ft-prose-pill--${obj.severity}`}>{obj.severity}</span>}
        {typeof obj.file === 'string' && <code>{obj.file}{obj.line ? `:${obj.line}` : ''}</code>}{' '}
        {clip(obj.comment as string, 200)}
      </span>
    );
  }

  // question-like { question, owner / for_team }
  if (typeof obj.question === 'string') {
    const owner = (obj.owner ?? obj.for_team ?? obj.should_ask) as string | undefined;
    return (
      <span>
        {owner && <span className="ft-prose-pill">{owner}</span>}
        {clip(obj.question, 240)}
      </span>
    );
  }

  // generic fallback — pull a few key fields
  const interestingKeys = Object.keys(obj).filter(k => typeof obj[k] === 'string' || typeof obj[k] === 'number').slice(0, 3);
  if (interestingKeys.length > 0) {
    return (
      <span>
        {interestingKeys.map((k, i) => (
          <span key={k}>{i > 0 && ' · '}<span className="ft-prose-label">{k}:</span> {clip(String(obj[k]), 80)}</span>
        ))}
      </span>
    );
  }
  return <span className="ft-prose-meta">[object with {Object.keys(obj).length} keys]</span>;
}

function prettyLabel(key: string): string {
  return key.replace(/_/g, ' ').replace(/\b\w/g, c => c.toUpperCase());
}

function clip(s: string, max: number): string {
  if (!s) return '';
  return s.length > max ? s.slice(0, max - 1) + '…' : s;
}

// ---------------------------------------------------------------------------
// JSON tree
// ---------------------------------------------------------------------------

function JsonNode({ value, keyName, depth }: { value: unknown; keyName: string | null; depth: number }) {
  const [open, setOpen] = useState(depth < 2);

  if (value === null) return <Leaf k={keyName} body={<span className="ft-null">null</span>} />;
  if (typeof value === 'string') return <Leaf k={keyName} body={<span className="ft-str">"{value}"</span>} />;
  if (typeof value === 'number') return <Leaf k={keyName} body={<span className="ft-num">{value}</span>} />;
  if (typeof value === 'boolean') return <Leaf k={keyName} body={<span className="ft-bool">{String(value)}</span>} />;

  if (Array.isArray(value)) {
    const empty = value.length === 0;
    return (
      <div className="ft-node">
        <div className="ft-node-header" onClick={() => !empty && setOpen(o => !o)}>
          {!empty && (open ? <ChevronDown size={11} /> : <ChevronRight size={11} />)}
          {keyName !== null && <span className="ft-key">{keyName}:</span>}
          <span className="ft-bracket">[</span>
          {!open && !empty && <span className="ft-summary">{value.length} items</span>}
          {!open && <span className="ft-bracket">]</span>}
        </div>
        {open && !empty && (
          <div className="ft-children">
            {value.map((item, i) => <JsonNode key={i} value={item} keyName={String(i)} depth={depth + 1} />)}
          </div>
        )}
        {open && <div className="ft-bracket-close"><span className="ft-bracket">]</span></div>}
      </div>
    );
  }

  if (typeof value === 'object') {
    const obj = value as Record<string, unknown>;
    const keys = Object.keys(obj);
    const empty = keys.length === 0;
    return (
      <div className="ft-node">
        <div className="ft-node-header" onClick={() => !empty && setOpen(o => !o)}>
          {!empty && (open ? <ChevronDown size={11} /> : <ChevronRight size={11} />)}
          {keyName !== null && <span className="ft-key">{keyName}:</span>}
          <span className="ft-bracket">{'{'}</span>
          {!open && !empty && <span className="ft-summary">{keys.length} {keys.length === 1 ? 'key' : 'keys'}</span>}
          {!open && <span className="ft-bracket">{'}'}</span>}
        </div>
        {open && !empty && (
          <div className="ft-children">
            {keys.map(k => <JsonNode key={k} value={obj[k]} keyName={k} depth={depth + 1} />)}
          </div>
        )}
        {open && <div className="ft-bracket-close"><span className="ft-bracket">{'}'}</span></div>}
      </div>
    );
  }

  return <Leaf k={keyName} body={<span>{String(value)}</span>} />;
}

function Leaf({ k, body }: { k: string | null; body: React.ReactNode }) {
  return (
    <div className="ft-leaf">
      {k !== null && <span className="ft-key">{k}:</span>}
      {body}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Code block
// ---------------------------------------------------------------------------

function CodeBlock({ lang, body }: { lang: string; body: string }) {
  const [expanded, setExpanded] = useState(false);
  const lines = body.split('\n');
  const isLong = lines.length > 18;
  const visible = expanded || !isLong ? lines : lines.slice(0, 18);

  return (
    <div className="ft-codeblock">
      <div className="ft-codeblock-head">
        <span className="ft-codeblock-lang">{lang || 'text'}</span>
        <span className="ft-codeblock-stat">{lines.length} lines</span>
      </div>
      <pre className="ft-codeblock-body">
        {visible.map((l, i) => (
          <div key={i} className="ft-code-line">
            <span className="ft-code-lineno">{i + 1}</span>
            <span>{l || ' '}</span>
          </div>
        ))}
        {!expanded && isLong && <div className="ft-code-fade" />}
      </pre>
      {isLong && (
        <button className="ft-toggle" onClick={() => setExpanded(v => !v)}>
          {expanded ? 'Show less' : `Show all ${lines.length} lines`}
        </button>
      )}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Plain text with linkify
// ---------------------------------------------------------------------------

function FormattedText({ text }: { text: string }) {
  // Split by URLs and render hyperlinks
  const urlRegex = /(https?:\/\/[^\s)]+)/g;
  const parts = text.split(urlRegex);
  return (
    <div className="ft-paragraphs">
      {parts.map((p, i) =>
        urlRegex.test(p) ? (
          <a key={i} href={p} target="_blank" rel="noopener noreferrer">{p}</a>
        ) : (
          <span key={i}>{p}</span>
        ),
      )}
    </div>
  );
}
