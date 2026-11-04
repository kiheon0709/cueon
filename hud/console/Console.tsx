import {useCallback, useEffect, useRef, useState} from 'react';
import {api, type Doc, type Entry, type Gap, type PageNotes, type Stats, type Status} from './api';
import {startMic, type MicEvent} from './mic';

const ms = (value: number | null | undefined) => (value == null ? '–' : `${Math.round(value)} ms`);

const QUESTION_TYPES = 12;

type Step = 'material' | 'cards' | 'present' | 'developer';

export default function Console() {
  const [status, setStatus] = useState<Status | null>(null);
  const [docs, setDocs] = useState<Doc[]>([]);
  const [entries, setEntries] = useState<Entry[]>([]);
  const [gaps, setGaps] = useState<Gap[]>([]);
  const [notes, setNotes] = useState<PageNotes[]>([]);
  const [stats, setStats] = useState<Stats | null>(null);
  const [error, setError] = useState('');
  const [step, setStep] = useState<Step | null>(null);

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
      // Open where the presenter left off: nothing yet means upload, cards ready means present.
      setStep(current => current ?? (b.entries.length ? 'present' : 'material'));
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
        if (status?.prep.running && !s.prep.running) {
          await refresh();
          if (!s.prep.error) setStep('cards');
        }
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

  const steps: {id: Step; label: string; note?: string}[] = [
    {id: 'material', label: 'Material', note: docs.length ? String(docs.length) : undefined},
    {id: 'cards', label: 'Cards', note: entries.length ? String(entries.length) : undefined},
    {id: 'present', label: 'Present'},
  ];

  return (
    <div className="console">
      <header className="top">
        <h1>Cueon</h1>
        <nav className="steps">
          {steps.map((item, index) => (
            <button key={item.id} className={step === item.id ? 'step step--on' : 'step'} onClick={() => setStep(item.id)}>
              <span className="step-num">{index + 1}</span>
              {item.label}
              {item.note && <span className="step-note">{item.note}</span>}
            </button>
          ))}
        </nav>
        <div className="top-end">
          {status?.fake && <span className="badge badge--warn">Demo mode: no API key</span>}
          {status?.backend === 'glimmer' && <span className="badge badge--ok">Local mode</span>}
          <button className={step === 'developer' ? 'link link--on' : 'link'} onClick={() => setStep('developer')}>
            Developer
          </button>
        </div>
      </header>
      {error && <p className="error banner">{error}</p>}

      {step === 'material' && <Material docs={docs} status={status} entries={entries} run={run} go={setStep} />}
      {step === 'cards' && <Cards entries={entries} gaps={gaps} notes={notes} run={run} go={setStep} />}
      {/* Stays mounted so the microphone and the lens keep running while you look at the cards. */}
      <div hidden={step !== 'present'}>
        <Present status={status} entries={entries} run={run} go={setStep} />
      </div>
      {step === 'developer' && <Developer status={status} stats={stats} />}
    </div>
  );
}

type Run = (action: () => Promise<unknown>) => Promise<void>;
type Go = (step: Step) => void;

function Material({docs, status, entries, run, go}: {docs: Doc[]; status: Status | null; entries: Entry[]; run: Run; go: Go}) {
  const [alias, setAlias] = useState('');
  const [dragging, setDragging] = useState(false);
  const fileRef = useRef<HTMLInputElement>(null);
  const prep = status?.prep;

  const send = (files: File[]) =>
    run(async () => {
      for (const file of files) {
        const form = new FormData();
        form.append('file', file);
        form.append('alias', files.length === 1 ? alias : '');
        form.append('role', '');
        await api('/api/docs', {method: 'POST', body: form});
      }
      setAlias('');
      if (fileRef.current) fileRef.current.value = '';
    });

  return (
    <main className="page page--narrow">
      <h2>What are you presenting?</h2>
      <p className="lede">Add your slides and anything that backs them up: plans, papers, data. Cueon answers only from these.</p>
      <label
        className={`drop${dragging ? ' drop--on' : ''}`}
        onDragOver={e => {
          e.preventDefault();
          setDragging(true);
        }}
        onDragLeave={() => setDragging(false)}
        onDrop={e => {
          e.preventDefault();
          setDragging(false);
          void send(Array.from(e.dataTransfer.files));
        }}
      >
        <b>Drop PDF or CSV files</b>
        <span>or click to choose</span>
        <input
          type="file"
          accept=".pdf,.csv"
          multiple
          hidden
          ref={fileRef}
          onChange={e => void send(Array.from(e.target.files ?? []))}
        />
      </label>
      <label className="field">
        Short name for citations, optional
        <input placeholder="BP" value={alias} onChange={e => setAlias(e.target.value)} size={10} />
      </label>

      {docs.length > 0 && (
        <ul className="docs">
          {docs.map(doc => (
            <li key={doc.alias}>
              <b>{doc.alias}</b>
              <span className="grow muted">{doc.name} · {doc.pages} pages</span>
              <select
                value={doc.role}
                aria-label={`Role of ${doc.alias}`}
                onChange={e => run(() => api(`/api/docs/${doc.alias}`, {method: 'PATCH', json: {role: e.target.value}}))}
              >
                <option value="main">What I present</option>
                <option value="evidence">Backup</option>
              </select>
              <button className="link" onClick={() => run(() => api(`/api/docs/${doc.alias}`, {method: 'DELETE'}))}>
                Remove
              </button>
            </li>
          ))}
        </ul>
      )}

      <div className="cta">
        <button
          className="primary"
          disabled={!docs.length || prep?.running}
          onClick={() => run(() => api('/api/prep', {method: 'POST', json: {limit: QUESTION_TYPES}}))}
        >
          {prep?.running ? 'Preparing…' : entries.length ? 'Prepare cards again' : 'Prepare cards'}
        </button>
        {entries.length > 0 && !prep?.running && (
          <button className="secondary" onClick={() => go('cards')}>Review {entries.length} cards</button>
        )}
      </div>
      {prep?.running && <p className="muted">{prep.message || 'Starting'}. This takes a few minutes.</p>}
      {prep?.error && <p className="error">{prep.error}</p>}
      {!prep?.running && !entries.length && (
        <p className="muted">Cueon predicts the questions you'll get, writes a card for each, and checks every number against the page it cites.</p>
      )}
    </main>
  );
}

function Cards({entries, gaps, notes, run, go}: {entries: Entry[]; gaps: Gap[]; notes: PageNotes[]; run: Run; go: Go}) {
  const parents = entries.filter(e => !e.parent);
  return (
    <main className="page page--narrow">
      <div className="page-head">
        <div>
          <h2>{entries.length ? `${entries.length} cards ready` : 'No cards yet'}</h2>
          <p className="lede">Each one appears on your lens exactly as written. Open any card to change it.</p>
        </div>
        {entries.length > 0 && <button className="primary" onClick={() => go('present')}>Rehearse</button>}
      </div>
      {!entries.length && <button className="secondary" onClick={() => go('material')}>Add material</button>}
      <Gaps gaps={gaps} run={run} />
      <ul className="cards">
        {parents.map(entry => (
          <CardRow key={entry.id} entry={entry} followUps={entries.filter(child => child.parent === entry.id)} run={run} />
        ))}
      </ul>
      {notes.length > 0 && (
        <details className="notes">
          <summary>Notes for each slide ({notes.length})</summary>
          {notes.map(n => (
            <div key={n.page} className="note">
              <b>p.{n.page}</b> {n.points.join(' · ')}
              {n.short && <div className="muted">Short version: {n.short}</div>}
              {n.support && <div className="muted">Backup: {n.support} ▸ {n.support_source}</div>}
            </div>
          ))}
        </details>
      )}
    </main>
  );
}

function CardRow({entry, followUps, run}: {entry: Entry; followUps: Entry[]; run: Run}) {
  const [open, setOpen] = useState(false);
  return (
    <li className={open ? 'card card--open' : 'card'}>
      <button className="card-head" aria-expanded={open} onClick={() => setOpen(!open)}>
        <span className="grow">
          <span className="card-lead">{entry.card.lead}</span>
          <span className="muted card-q">{entry.question}</span>
        </span>
        {entry.edited && <span className="tag">edited</span>}
        <span className="muted">{entry.card.source}</span>
      </button>
      {open && (
        <div className="card-body">
          <EntryEditor entry={entry} run={run} />
          {followUps.length > 0 && <h3>If they follow up</h3>}
          {followUps.map(child => (
            <EntryEditor key={child.id} entry={child} run={run} />
          ))}
        </div>
      )}
    </li>
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
      <div className="card-view">
        <div className="lens">
          <div className="lens-lead">{entry.card.lead}</div>
          {entry.card.points.map(p => (
            <div key={p}>{p}</div>
          ))}
          <div className="lens-source">{entry.card.source}</div>
        </div>
        <div className="card-actions">
          <button className="link" onClick={() => setEditing(true)}>Edit</button>
          <button className="link" onClick={() => run(() => api(`/api/bank/${entry.id}`, {method: 'DELETE'}))}>Delete</button>
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
        <button className="primary" onClick={save}>Save</button>
        <button className="link" onClick={() => setEditing(false)}>Close</button>
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
    <section className="gaps">
      <h3>{gaps.length === 1 ? '1 question your material can\'t answer' : `${gaps.length} questions your material can't answer`}</h3>
      {gaps.map(gap => (
        <div key={gap.question} className="gap">
          <b>{gap.question}</b>
          {gap.problems.map(p => (
            <div key={p} className="muted">{p}</div>
          ))}
          {open === gap.question ? (
            <div className="row">
              <input className="grow" placeholder="What you'd say" value={lead} onChange={e => setLead(e.target.value)} />
              <input placeholder="Source, optional" value={source} onChange={e => setSource(e.target.value)} size={12} />
              <button
                className="secondary"
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
            <button className="link" onClick={() => setOpen(gap.question)}>Write my own answer</button>
          )}
        </div>
      ))}
    </section>
  );
}

function Present({status, entries, run, go}: {status: Status | null; entries: Entry[]; run: Run; go: Go}) {
  const [text, setText] = useState('');
  const [heard, setHeard] = useState('');
  const [micError, setMicError] = useState('');
  const stopRef = useRef<(() => void) | null>(null);
  const [micOn, setMicOn] = useState(false);
  const glasses = import.meta.env.DEV ? '/' : '/glasses';
  const mode = status?.mode ?? 'qa';
  const listening = !!status?.listening;

  const stopMic = () => {
    stopRef.current?.();
    stopRef.current = null;
    setMicOn(false);
  };

  const openMic = async () => {
    if (stopRef.current) return true;
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
      return true;
    } catch (e) {
      setMicError((e as Error).message);
      return false;
    }
  };

  const listen = async () => {
    if (!listening && status?.stt && !(await openMic())) return;
    if (!listening) setHeard('');
    await run(() => api('/api/listen', {method: 'POST'}));
  };

  const follow = () => (micOn ? stopMic() : void openMic());

  const setMode = (next: 'qa' | 'present') => run(() => api('/api/mode', {method: 'POST', json: {mode: next}}));

  const say = () =>
    run(async () => {
      if (!text.trim()) return;
      setHeard(text);
      await api('/api/ask', {method: 'POST', json: {text}});
      setText('');
    });

  return (
    <main className="page present">
      <div className="lens-frame">
        <iframe title="Glasses view" src={glasses} width={600} height={600} inert />
        <p className="muted">What your lens shows</p>
      </div>

      <div className="controls">
        <div className="seg">
          <button className={mode === 'present' ? 'on' : ''} onClick={() => setMode('present')}>While presenting</button>
          <button className={mode === 'qa' ? 'on' : ''} onClick={() => setMode('qa')}>During Q&amp;A</button>
        </div>

        {!entries.length && (
          <p className="muted">
            No cards yet. <button className="link" onClick={() => go('material')}>Add your material first</button>
          </p>
        )}

        {mode === 'qa' ? (
          <>
            <button className={listening ? 'hero hero--on' : 'hero'} onClick={listen}>
              {listening ? 'Listening… tap to stop' : 'Listen to a question'}
            </button>
            <p className="muted">
              {status?.stt
                ? 'Tap once for each question. The right card appears on your lens when the person stops talking.'
                : 'Speech needs an API key. Type a question below.'}
            </p>
          </>
        ) : (
          <>
            <button className={micOn ? 'hero hero--on' : 'hero'} disabled={!status?.stt} onClick={follow}>
              {micOn ? 'Following you… tap to stop' : 'Follow my talk'}
            </button>
            <p className="muted">Cueon tracks your slide as you speak and tells you when you skip a point.</p>
            <div className="row">
              <label className="field field--inline">
                Talk length, minutes
                <input
                  type="number"
                  min={0}
                  step={0.5}
                  defaultValue={status?.talk_minutes || ''}
                  onBlur={e => run(() => api('/api/talk', {method: 'POST', json: {minutes: +e.target.value || 0}}))}
                />
              </label>
              <button className="secondary" onClick={() => run(() => api('/api/talk/start', {method: 'POST'}))}>Start clock</button>
            </div>
            <div className="row">
              <button className="secondary" onClick={() => run(() => api('/api/page/-1', {method: 'POST'}))}>Previous slide</button>
              <button className="secondary" onClick={() => run(() => api('/api/page/1', {method: 'POST'}))}>Next slide</button>
            </div>
          </>
        )}

        {heard && (
          <div className="heard">
            <span className="muted">Heard</span>
            {heard}
          </div>
        )}
        {micError && <p className="error">{micError}</p>}

        <div className="type-box">
          <label htmlFor="say">{mode === 'qa' ? 'Or type a question to rehearse' : 'Or type a sentence to rehearse'}</label>
          <div className="row">
            <input
              id="say"
              className="grow"
              placeholder={mode === 'qa' ? 'Can I use this with a confidential deck?' : 'Today I want to talk about…'}
              value={text}
              onChange={e => setText(e.target.value)}
              onKeyDown={e => e.key === 'Enter' && say()}
            />
            <button className="secondary" onClick={say}>Send</button>
          </div>
        </div>
        {micOn && mode === 'qa' && (
          <button className="link" onClick={stopMic}>Turn the microphone off</button>
        )}
      </div>
    </main>
  );
}

function Developer({status, stats}: {status: Status | null; stats: Stats | null}) {
  return (
    <main className="page page--narrow">
      <h2>Developer</h2>
      <p className="lede">
        {status?.model} · {status?.backend} · glasses connected: {status?.hud_clients ?? 0}
        {status?.prep.stats && status.prep.stats.questions > 0 && (
          <>
            <br />
            Checks: {status.prep.stats.first_try}/{status.prep.stats.questions} passed on the first draft,{' '}
            {status.prep.stats.retried} fixed after feedback, {status.prep.stats.gaps} rejected, {status.prep.stats.drafts} drafts
            {status.prep.vision_pages ? `, numbers read from ${status.prep.vision_pages} chart pages` : ''}
          </>
        )}
      </p>
      <Latency stats={stats} />
    </main>
  );
}

function Latency({stats}: {stats: Stats | null}) {
  if (!stats) return null;
  const rate = stats.hit_rate == null ? '–' : `${Math.round(stats.hit_rate * 100)}%`;
  return (
    <div>
      <h3>Latency & hit rate</h3>
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
      <p className="muted">Measured from the end of the question (speech complete) to the card text / to the glasses rendering it.</p>
      <ul className="recent">
        {stats.recent.map(r => (
          <li key={r.id}>
            <span className={`tag tag--${r.path}`}>{r.path}</span> {r.question}{' '}
            <span className="muted">
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
              <li key={i} className="muted">
                {c.task}: {c.cached.toLocaleString()} / {c.prompt.toLocaleString()} tokens cached · {ms(c.ms)}
              </li>
            ))}
          </ul>
        </>
      )}
    </div>
  );
}
