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
        <JsonNode value={parsed.value} keyName={null} depth={0} />
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

  // Fenced code blocks first — common in agent responses
  const fenced = extractFencedBlocks(trimmed);
  if (fenced.blocks.length > 0) {
    // If the block is JSON, flatten to the JSON path
    if (fenced.blocks.length === 1 && (fenced.blocks[0].lang === 'json' || fenced.blocks[0].lang === '')) {
      const body = fenced.blocks[0].body.trim();
      if (looksLikeJson(body)) {
        try { return { kind: 'json', value: JSON.parse(body), preamble: fenced.preamble }; }
        catch { /* fall through */ }
      }
    }
    return { kind: 'code', blocks: fenced.blocks, preamble: fenced.preamble };
  }

  // No fences — try to find a JSON object/array by locating the first { or [
  const firstBrace = Math.min(...['{', '['].map(c => {
    const i = trimmed.indexOf(c);
    return i === -1 ? Infinity : i;
  }));
  if (firstBrace !== Infinity) {
    const candidate = trimmed.slice(firstBrace);
    if (looksLikeJson(candidate)) {
      try {
        return { kind: 'json', value: JSON.parse(candidate), preamble: trimmed.slice(0, firstBrace).trim() };
      } catch { /* not parseable */ }
    }
  }

  return { kind: 'text' };
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
