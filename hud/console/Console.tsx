import {useCallback, useEffect, useRef, useState} from 'react';
import {api, type Doc, type Entry, type Gap, type PageNotes, type Stats, type Status} from './api';
import {startMic, type MicEvent} from './mic';

const ms = (value: number | null | undefined) => (value == null ? '–' : `${Math.round(value)} ms`);

export default function Console() {
  const [status, setStatus] = useState<Status | null>(null);
  const [docs, setDocs] = useState<Doc[]>([]);
  const [entries, setEntries] = useState<Entry[]>([]);
  const [gaps, setGaps] = useState<Gap[]>([]);
  const [notes, setNotes] = useState<PageNotes[]>([]);
  const [stats, setStats] = useState<Stats | null>(null);
  const [error, setError] = useState('');

  const refresh = useCallback(async () => {
    try {
      const [s, d, b, n, st] = await Promise.all([
        api<Status>('/api/status'),
        api<Doc[]>('/api/docs'),
        api<{entries: Entry[]; gaps: Gap[]}>('/api/bank'),
        api<PageNotes[]>('/api/notes'),
        api<Stats>('/api/stats'),
      ]);
      setStatus(s);
      setDocs(d);
      setEntries(b.entries);
      setGaps(b.gaps);
      setNotes(n);
      setStats(st);
      setError('');
    } catch (e) {
      setError(`Hub not reachable: ${(e as Error).message}`);
    }
  }, []);

  useEffect(() => {
    void refresh();
  }, [refresh]);

  // Poll while prep runs, and keep latency numbers fresh.
  useEffect(() => {
    const timer = window.setInterval(async () => {
      try {
        const [s, st] = await Promise.all([api<Status>('/api/status'), api<Stats>('/api/stats')]);
        if (status?.prep.running && !s.prep.running) void refresh();
        setStatus(s);
        setStats(st);
      } catch {
        /* shown on the next full refresh */
      }
    }, 1000);
    return () => window.clearInterval(timer);
  }, [status?.prep.running, refresh]);

  const run = async (action: () => Promise<unknown>) => {
    try {
      await action();
      await refresh();
    } catch (e) {
      setError((e as Error).message);
    }
  };

  return (
    <div className="console">
      <header className="top">
        <h1>Cueon</h1>
        {status && (
          <span className={`badge ${status.fake ? 'badge--warn' : 'badge--ok'}`}>
            {status.fake
              ? 'Stand-in models (no API key)'
              : status.backend === 'glimmer'
                ? `Local mode · ${status.model} (material stays on this machine)`
                : status.model}
          </span>
        )}
        {status && <span className="badge">Glasses connected: {status.hud_clients}</span>}
        {error && <span className="error">{error}</span>}
      </header>

      <div className="columns">
        <section className="left">
          <Material docs={docs} run={run} />
          <Prep status={status} entries={entries} gaps={gaps} run={run} />
          <Bank entries={entries} run={run} />
          <Gaps gaps={gaps} run={run} />
          <Notes notes={notes} />
        </section>

        <section className="right">
          <Live status={status} run={run} />
          <Latency stats={stats} />
        </section>
      </div>
    </div>
  );
}

type Run = (action: () => Promise<unknown>) => Promise<void>;

function Material({docs, run}: {docs: Doc[]; run: Run}) {
  const [alias, setAlias] = useState('');
  const [role, setRole] = useState('');
  const fileRef = useRef<HTMLInputElement>(null);

  const [dragging, setDragging] = useState(false);

  const send = (file: File) =>
    run(async () => {
      const form = new FormData();
      form.append('file', file);
      form.append('alias', alias);
      form.append('role', role);
      await api('/api/docs', {method: 'POST', body: form});
      setAlias('');
      if (fileRef.current) fileRef.current.value = '';
    });

  const upload = () => {
    const file = fileRef.current?.files?.[0];
    if (file) void send(file);
  };

  return (
    <div className="panel">
      <h2>1 · Material</h2>
      <p className="hint">Slides, plans, papers, data. Cards cite pages as “ALIAS p.N”.</p>
      <div
        className={`drop${dragging ? ' drop--on' : ''}`}
        onDragOver={e => {
          e.preventDefault();
          setDragging(true);
        }}
        onDragLeave={() => setDragging(false)}
        onDrop={e => {
          e.preventDefault();
          setDragging(false);
          Array.from(e.dataTransfer.files).forEach(file => void send(file));
        }}
      >
        Drop PDF or CSV files here (alias and role below apply to the next file)
      </div>
      <div className="row">
        <input type="file" accept=".pdf,.csv" ref={fileRef} />
        <input placeholder="Alias (e.g. BP)" value={alias} onChange={e => setAlias(e.target.value)} size={10} />
        <select value={role} onChange={e => setRole(e.target.value)}>
          <option value="">Role: auto</option>
          <option value="main">Main (what you present)</option>
          <option value="evidence">Evidence</option>
        </select>
        <button onClick={upload}>Upload</button>
      </div>
      <table>
        <tbody>
          {docs.map(doc => (
            <tr key={doc.alias}>
              <td><b>{doc.alias}</b></td>
              <td>{doc.name}</td>
              <td>{doc.pages} p.</td>
              <td>
                <select
                  value={doc.role}
                  onChange={e => run(() => api(`/api/docs/${doc.alias}`, {method: 'PATCH', json: {role: e.target.value}}))}
                >
                  <option value="main">main</option>
                  <option value="evidence">evidence</option>
                </select>
              </td>
              <td>
                <button className="ghost" onClick={() => run(() => api(`/api/docs/${doc.alias}`, {method: 'DELETE'}))}>
                  Remove
                </button>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function Prep({status, entries, gaps, run}: {status: Status | null; entries: Entry[]; gaps: Gap[]; run: Run}) {
  const [limit, setLimit] = useState(12);
  const prep = status?.prep;
  return (
    <div className="panel">
      <h2>2 · Prepare</h2>
      <p className="hint">
        Predicts likely questions, writes a card for each from your material, checks every number and claim, and
        retries up to 3 times. What can't be supported shows up as a gap.
      </p>
      <div className="row">
        <label>
          Question types <input type="number" min={3} max={30} value={limit} onChange={e => setLimit(+e.target.value)} />
        </label>
        <button disabled={prep?.running} onClick={() => run(() => api('/api/prep', {method: 'POST', json: {limit}}))}>
          {prep?.running ? 'Preparing…' : 'Prepare cards'}
        </button>
        <span className="hint">{prep?.error ? `Error: ${prep.error}` : prep?.message}</span>
      </div>
      <p>
        <b>{entries.length}</b> cards · <b>{entries.filter(e => e.parent).length}</b> follow-ups · <b>{gaps.length}</b> gaps
      </p>
      {prep?.stats && prep.stats.questions > 0 && (
        <p className="hint">
          Checks: {prep.stats.first_try}/{prep.stats.questions} cards passed on the first draft,{' '}
          {prep.stats.retried} fixed after feedback, {prep.stats.gaps} rejected after 3 tries ·{' '}
          {prep.stats.drafts} drafts written
          {prep.vision_pages ? ` · numbers read from ${prep.vision_pages} chart pages` : ''}
        </p>
      )}
    </div>
  );
}

function Bank({entries, run}: {entries: Entry[]; run: Run}) {
  const parents = entries.filter(e => !e.parent);
  return (
    <div className="panel">
      <h2>3 · Card bank</h2>
      <p className="hint">Matched cards are shown exactly as written here. Edit anything; your edits survive re-prep.</p>
      {parents.map(entry => (
        <div key={entry.id} className="entry">
          <EntryEditor entry={entry} run={run} />
          {entries
            .filter(child => child.parent === entry.id)
            .map(child => (
              <div key={child.id} className="followup">
                <span className="tag">follow-up</span>
                <EntryEditor entry={child} run={run} />
              </div>
            ))}
        </div>
      ))}
      {parents.length === 0 && <p className="hint">No cards yet.</p>}
    </div>
  );
}

function EntryEditor({entry, run}: {entry: Entry; run: Run}) {
  const [editing, setEditing] = useState(false);
  const [question, setQuestion] = useState(entry.question);
  const [variants, setVariants] = useState(entry.variants.join('\n'));
  const [lead, setLead] = useState(entry.card.lead);
  const [points, setPoints] = useState(entry.card.points.join('\n'));
  const [source, setSource] = useState(entry.card.source ?? '');
  const [problems, setProblems] = useState<string[]>([]);

  if (!editing) {
    return (
      <div className="card-view" onDoubleClick={() => setEditing(true)}>
        <div className="q">
          <span className="tag">{entry.qtype}</span>
          {entry.audience && <span className="tag">{entry.audience}</span>} {entry.question}
          {entry.edited && <span className="tag tag--edited">edited</span>}
          {entry.hits > 0 && <span className="tag tag--hit">hit ×{entry.hits}</span>}
        </div>
        <div className="lens">
          <div className="lens-lead">{entry.card.lead}</div>
          {entry.card.points.slice(0, 2).map(p => (
            <div key={p}>{p}</div>
          ))}
          {entry.card.points.length > 2 && <div className="lens-more">+{entry.card.points.length - 2} on swipe down</div>}
          <div className="lens-source">{entry.card.source}</div>
        </div>
        <div className="hint">Matches: {[entry.question, ...entry.variants].join(' · ')}</div>
        <div className="meta">
          <button className="ghost" onClick={() => setEditing(true)}>Edit</button>
          <button className="ghost" onClick={() => run(() => api(`/api/bank/${entry.id}`, {method: 'DELETE'}))}>
            Delete
          </button>
        </div>
      </div>
    );
  }

  const save = () =>
    run(async () => {
      const result = await api<{problems: string[]}>(`/api/bank/${entry.id}`, {
        method: 'PUT',
        json: {
          question,
          variants: variants.split('\n'),
          lead,
          points: points.split('\n').filter(p => p.trim()),
          source: source || null,
        },
      });
      setProblems(result.problems);
      if (!result.problems.length) setEditing(false);
    });

  return (
    <div className="card-edit">
      <label>Question<input value={question} onChange={e => setQuestion(e.target.value)} /></label>
      <label>Phrasings it should match (one per line)<textarea rows={3} value={variants} onChange={e => setVariants(e.target.value)} /></label>
      <label>Lead<input value={lead} onChange={e => setLead(e.target.value)} /></label>
      <label>Points (one per line, max 3)<textarea rows={3} value={points} onChange={e => setPoints(e.target.value)} /></label>
      <label>Source<input value={source} onChange={e => setSource(e.target.value)} placeholder="BP p.12" /></label>
      {problems.map(p => (
        <p key={p} className="error">⚠ {p}</p>
      ))}
      <div className="row">
        <button onClick={save}>Save</button>
        <button className="ghost" onClick={() => setEditing(false)}>Close</button>
      </div>
    </div>
  );
}

function Gaps({gaps, run}: {gaps: Gap[]; run: Run}) {
  const [open, setOpen] = useState<string | null>(null);
  const [lead, setLead] = useState('');
  const [source, setSource] = useState('');
  if (gaps.length === 0) return null;
  return (
    <div className="panel">
      <h2>Gaps · your material doesn't answer these</h2>
      <p className="hint">Decide how you'll answer, or add the evidence and prepare again.</p>
      {gaps.map(gap => (
        <div key={gap.question} className="gap">
          <b>{gap.question}</b>
          <ul>
            {gap.problems.map(p => (
              <li key={p} className="hint">{p}</li>
            ))}
          </ul>
          {open === gap.question ? (
            <div className="row">
              <input placeholder="Your answer (lead)" value={lead} onChange={e => setLead(e.target.value)} />
              <input placeholder="Source (optional)" value={source} onChange={e => setSource(e.target.value)} size={10} />
              <button
                onClick={() =>
                  run(async () => {
                    await api('/api/bank', {method: 'POST', json: {question: gap.question, lead, source: source || null}});
                    setOpen(null);
                    setLead('');
                    setSource('');
                  })
                }
              >
                Add card
              </button>
            </div>
          ) : (
            <button className="ghost" onClick={() => setOpen(gap.question)}>Write my own card</button>
          )}
        </div>
      ))}
    </div>
  );
}

function Notes({notes}: {notes: PageNotes[]}) {
  if (notes.length === 0) return null;
  return (
    <div className="panel">
      <h2>Presentation notes</h2>
      <p className="hint">Written before the talk. During the talk nothing is generated; Cueon follows along and flags skipped points.</p>
      {notes.map(n => (
        <div key={n.page} className="note">
          <b>p.{n.page}</b> {n.points.join(' · ')}
          {n.short && <div className="hint">Short: {n.short}</div>}
          {n.support && (
            <div className="hint">
              Backup: {n.support} ▸ {n.support_source}
            </div>
          )}
        </div>
      ))}
    </div>
  );
}

function Live({status, run}: {status: Status | null; run: Run}) {
  const [text, setText] = useState('');
  const [heard, setHeard] = useState('');
  const [micError, setMicError] = useState('');
  const stopRef = useRef<(() => void) | null>(null);
  const [micOn, setMicOn] = useState(false);
  const glasses = import.meta.env.DEV ? '/' : '/glasses';
  const mode = status?.mode ?? 'qa';

  const toggleMic = async () => {
    if (stopRef.current) {
      stopRef.current();
      stopRef.current = null;
      setMicOn(false);
      return;
    }
    try {
      setMicError('');
      stopRef.current = await startMic((event: MicEvent) => {
        if (event.type === 'error') setMicError(event.message ?? 'error');
        if (event.type === 'closed') {
          stopRef.current = null;
          setMicOn(false);
        }
        if (event.transcript) setHeard(event.transcript);
      });
      setMicOn(true);
    } catch (e) {
      setMicError((e as Error).message);
    }
  };

  const say = () =>
    run(async () => {
      if (!text.trim()) return;
      setHeard(text);
      await api('/api/ask', {method: 'POST', json: {text}});
      setText('');
    });

  return (
    <div className="panel">
      <h2>4 · Rehearse / live</h2>
      <div className="row">
        <div className="seg">
          <button className={mode === 'present' ? 'on' : ''} onClick={() => run(() => api('/api/mode', {method: 'POST', json: {mode: 'present'}}))}>
            Presenting
          </button>
          <button className={mode === 'qa' ? 'on' : ''} onClick={() => run(() => api('/api/mode', {method: 'POST', json: {mode: 'qa'}}))}>
            Q&amp;A
          </button>
        </div>
        {mode === 'qa' ? (
          <button className={status?.listening ? 'on' : ''} onClick={() => run(() => api('/api/listen', {method: 'POST'}))}>
            {status?.listening ? '● Listening' : 'Listen (pinch-up)'}
          </button>
        ) : (
          <>
            <label className="hint">
              Talk length{' '}
              <input
                type="number"
                min={0}
                step={0.5}
                defaultValue={status?.talk_minutes || ''}
                placeholder="min"
                onBlur={e => run(() => api('/api/talk', {method: 'POST', json: {minutes: +e.target.value || 0}}))}
              />
            </label>
            <button onClick={() => run(() => api('/api/talk/start', {method: 'POST'}))}>Start clock</button>
            <button className="ghost" onClick={() => run(() => api('/api/page/-1', {method: 'POST'}))}>◀ Page</button>
            <button className="ghost" onClick={() => run(() => api('/api/page/1', {method: 'POST'}))}>Page ▶</button>
          </>
        )}
        <button className={micOn ? 'on' : ''} disabled={!status?.stt} onClick={toggleMic} title={status?.stt ? '' : 'Needs MODEL_API_KEY'}>
          {micOn ? '■ Mic on' : '🎙 Mic'}
        </button>
      </div>
      <div className="row">
        <input
          className="grow"
          placeholder={mode === 'qa' ? 'Type a question as the audience would ask it' : 'Type a sentence as you would say it'}
          value={text}
          onChange={e => setText(e.target.value)}
          onKeyDown={e => e.key === 'Enter' && say()}
        />
        <button onClick={say}>Say</button>
      </div>
      {heard && <p className="hint">Heard: “{heard}”</p>}
      {micError && <p className="error">{micError}</p>}
      <div className="glasses">
        <iframe title="Glasses view" src={glasses} width={600} height={600} />
      </div>
    </div>
  );
}

function Latency({stats}: {stats: Stats | null}) {
  if (!stats) return null;
  const rate = stats.hit_rate == null ? '–' : `${Math.round(stats.hit_rate * 100)}%`;
  return (
    <div className="panel">
      <h2>Latency & hit rate</h2>
      <p>
        <b>{stats.questions}</b> questions · prepared-card hit rate <b>{rate}</b>
      </p>
      <table>
        <thead>
          <tr>
            <th>Path</th>
            <th>n</th>
            <th>first text p50</th>
            <th>p95</th>
            <th>on lens p50</th>
            <th>p95</th>
          </tr>
        </thead>
        <tbody>
          {(['bank', 'live'] as const).map(path => {
            const p = stats.paths[path];
            return (
              <tr key={path}>
                <td>{path === 'bank' ? 'Prepared card' : 'Live (Spark)'}</td>
                <td>{p.count}</td>
                <td>{ms(p.first_p50)}</td>
                <td>{ms(p.first_p95)}</td>
                <td>{ms(p.rendered_p50)}</td>
                <td>{ms(p.rendered_p95)}</td>
              </tr>
            );
          })}
        </tbody>
      </table>
      <p className="hint">Measured from the end of the question (speech complete) to the card text / to the glasses rendering it.</p>
      <ul className="recent">
        {stats.recent.map(r => (
          <li key={r.id}>
            <span className={`tag tag--${r.path}`}>{r.path}</span> {r.question}{' '}
            <span className="hint">
              {r.qtype ? `→ ${r.qtype} (${r.score}) ` : ''}
              {ms(r.first)}
              {r.rendered ? ` / ${ms(r.rendered)}` : ''}
              {r.speculative ? ' · started early' : ''}
              {r.tentative ? ' · fallback card shown' : ''}
              {r.error ? ` · ${r.error}` : ''}
            </span>
          </li>
        ))}
      </ul>
      {stats.cache.length > 0 && (
        <>
          <h3>Prompt cache</h3>
          <ul className="recent">
            {stats.cache.slice(0, 8).map((c, i) => (
              <li key={i} className="hint">
                {c.task}: {c.cached.toLocaleString()} / {c.prompt.toLocaleString()} tokens cached · {ms(c.ms)}
              </li>
            ))}
          </ul>
        </>
      )}
    </div>
  );
}
