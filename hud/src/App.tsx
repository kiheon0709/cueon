import {useEffect, useState} from 'react';
import {App as WearablesApp, TextColor, TextStyle, TextView} from '@wearables-ui-toolkit/mrbd';
import {type CuePoint, useHub} from './useHub';

// Card dims after this long so the presenter looks back at the audience.
const DIM_AFTER_MS = 10_000;

function useNow(active: boolean): number {
  const [now, setNow] = useState(Date.now());
  useEffect(() => {
    if (!active) return;
    const timer = window.setInterval(() => setNow(Date.now()), 1000);
    return () => window.clearInterval(timer);
  }, [active]);
  return now;
}

function clock(ms: number): string {
  const total = Math.max(0, Math.round(ms / 1000));
  return `${Math.floor(total / 60)}:${String(total % 60).padStart(2, '0')}`;
}

export default function App() {
  const {message, connected, send} = useHub();
  const now = useNow(!!message.ends_at);
  const timer = message.ends_at ? (
    <TextView textStyle={TextStyle.META1} textColor={message.behind ? TextColor.ACCENT : TextColor.SECONDARY}>
      {clock(message.ends_at - now)} left · {message.pages_left} to go{message.behind ? ' · speed up' : ''}
    </TextView>
  ) : null;
  const answerPoints = (message.state === 'card' ? message.points : []) as string[] | undefined;
  const cuePoints = (message.state === 'present' || message.state === 'missed' ? message.points : []) as CuePoint[] | undefined;
  const [detail, setDetail] = useState(false);
  const [dimmed, setDimmed] = useState(false);

  // New card: reset detail/dim and tell the hub it was rendered (latency log).
  useEffect(() => {
    setDetail(false);
    setDimmed(false);
    if (message.state !== 'card') return;
    if (!message.replay) send({type: 'rendered', id: message.id});
    const timer = window.setTimeout(() => setDimmed(true), DIM_AFTER_MS);
    return () => window.clearTimeout(timer);
  }, [message]);

  // Neural Band arrives as key events: pinch = Enter, swipe up = ArrowUp.
  useEffect(() => {
    const onKey = (event: KeyboardEvent) => {
      if (event.key === 'Enter' && message.state === 'card') {
        setDetail(current => !current);
        setDimmed(false);
      } else if (event.key === 'ArrowUp') {
        send({type: 'toggle_listen'});
      } else if (event.key === 'ArrowRight' || event.key === 'ArrowLeft') {
        // Presentation mode: swipe to correct the tracked page.
        send({type: 'page', delta: event.key === 'ArrowRight' ? 1 : -1});
      }
    };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [message.state]);

  return (
    <WearablesApp>
      <main className={`hud${dimmed ? ' hud--dimmed' : ''}`} aria-live="polite">
        {message.state === 'idle' && (
          <span className={`dot${connected ? '' : ' dot--offline'}`} aria-label={connected ? 'Ready' : 'Offline'} />
        )}

        {message.state === 'listening' && (
          <div className="stack">
            <TextView textStyle={TextStyle.META1_EMPHASIZED} textColor={TextColor.ACCENT}>● Listening</TextView>
            <TextView textStyle={TextStyle.BODY2} textColor={TextColor.SECONDARY} className="clamp2">
              {message.partial}
            </TextView>
          </div>
        )}

        {message.state === 'thinking' && (
          <div className="stack">
            <TextView textStyle={TextStyle.META1} textColor={TextColor.SECONDARY}>Q {message.question}</TextView>
            <TextView textStyle={TextStyle.BODY1}>Good question — short answer is…</TextView>
          </div>
        )}

        {message.state === 'card' && (
          <div className="stack">
            <TextView textStyle={TextStyle.META1} textColor={TextColor.SECONDARY} className="clamp2">
              Q {message.question}
            </TextView>
            <hr className="rule" />
            <TextView textStyle={TextStyle.HEADING1}>{message.lead}</TextView>
            {(detail ? answerPoints : answerPoints?.slice(0, 2))?.map(point => (
              <TextView key={point} textStyle={TextStyle.BODY2}>• {point}</TextView>
            ))}
            <div className="foot">
              {message.live && (
                <TextView textStyle={TextStyle.META1} textColor={TextColor.SECONDARY}>
                  Live · unchecked
                </TextView>
              )}
              {message.tentative && (
                <TextView textStyle={TextStyle.META1} textColor={TextColor.SECONDARY}>
                  Closest prepared · updating…
                </TextView>
              )}
              {!!message.choices && message.choices > 1 && (
                <TextView textStyle={TextStyle.META1} textColor={TextColor.SECONDARY}>
                  {message.choice ?? 1}/{message.choices} ◂▸
                </TextView>
              )}
              {message.source && (
                <TextView textStyle={TextStyle.META1} textColor={TextColor.ACCENT} className="source">
                  ▸ {message.source}
                </TextView>
              )}
            </div>
          </div>
        )}

        {message.state === 'repeat' && (
          <div className="stack">
            <TextView textStyle={TextStyle.HEADING2}>Ask to repeat</TextView>
            {message.partial && (
              <TextView textStyle={TextStyle.BODY2} textColor={TextColor.SECONDARY}>“{message.partial}”</TextView>
            )}
          </div>
        )}

        {message.state === 'present' && (
          <div className="stack">
            <div className="foot">
              <TextView textStyle={TextStyle.META1} textColor={TextColor.SECONDARY}>
                {message.page}/{message.total} · {message.title}
              </TextView>
              {timer}
            </div>
            {message.short && (
              <TextView textStyle={TextStyle.BODY1} textColor={TextColor.ACCENT}>
                Short: {message.short}
              </TextView>
            )}
            {cuePoints?.map(point => (
              <TextView
                key={point.text}
                textStyle={TextStyle.BODY2}
                textColor={point.done ? TextColor.SECONDARY : TextColor.PRIMARY}
                className={point.done ? 'done' : undefined}
              >
                {point.done ? '✓' : '○'} {point.text}
              </TextView>
            ))}
          </div>
        )}

        {message.state === 'missed' && (
          <div className="stack">
            <TextView textStyle={TextStyle.META1_EMPHASIZED} textColor={TextColor.ACCENT}>Skipped</TextView>
            {message.missed?.map(point => (
              <TextView key={point} textStyle={TextStyle.HEADING2}>{point}</TextView>
            ))}
            <TextView textStyle={TextStyle.META1} textColor={TextColor.SECONDARY}>
              Now {message.page}/{message.total} · {message.title}
            </TextView>
          </div>
        )}
      </main>
    </WearablesApp>
  );
}
