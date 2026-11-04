import {useEffect, useState} from 'react';
import {Button, ButtonRail, App as WearablesApp, TextColor, TextStyle, TextView} from '@wearables-ui-toolkit/mrbd';
import {type CuePoint, useHub} from './useHub';

const MAX_PARTIAL = 190;

function useNow(active: boolean): number {
  const [now, setNow] = useState(Date.now());
  useEffect(() => {
    if (!active) return;
    setNow(Date.now());
    const tick = window.setInterval(() => setNow(Date.now()), 1000);
    return () => window.clearInterval(tick);
  }, [active]);
  return now;
}

function clock(ms: number): string {
  const total = Math.max(0, Math.round(ms / 1000));
  return `${Math.floor(total / 60)}:${String(total % 60).padStart(2, '0')}`;
}

export default function App() {
  const {message, connected, send} = useHub();
  const [detail, setDetail] = useState(false);
  const now = useNow(!!message.ends_at);
  const answerPoints = (message.state === 'card' ? message.points : []) as string[] | undefined;
  const cuePoints = (message.state === 'present' || message.state === 'missed' ? message.points : []) as
    | CuePoint[]
    | undefined;

  // New card: collapse detail and tell the hub it was rendered (latency log).
  useEffect(() => {
    setDetail(false);
    // The fallback card isn't the answer: only the real card counts for latency.
    if (message.state === 'card' && !message.replay && !message.dimmed && !message.tentative) {
      send({type: 'rendered', id: message.id});
    }
  }, [message.id, message.state, message.lead]);

  // Neural Band arrives as key events. Pinch (Enter) activates the focused button; swipes are arrows:
  // up = listen, down = show all points, left/right = other card or correct the page.
  useEffect(() => {
    const onKey = (event: KeyboardEvent) => {
      if (event.key === 'ArrowDown' && message.state === 'card') {
        setDetail(current => !current);
      } else if (event.key === 'ArrowUp') {
        send({type: 'toggle_listen'});
      } else if (event.key === 'ArrowRight' || event.key === 'ArrowLeft') {
        send({type: 'page', delta: event.key === 'ArrowRight' ? 1 : -1});
      }
    };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [message.state]);

  const status = message.tentative
    ? 'CLOSEST PREPARED'
    : message.writing
      ? 'LIVE · WRITING'
      : message.live
      ? message.source
        ? 'LIVE · FROM YOUR MATERIAL'
        : 'REASONED · NOT FROM YOUR MATERIAL'
      : message.choices && message.choices > 1
        ? `${message.choice ?? 1} OF ${message.choices}`
        : null;

  const presenting = message.state === 'present' || message.state === 'missed';
  const listening = message.state === 'listening';
  const action = presenting ? 'Start Q&A' : listening ? 'Stop' : 'Listen';
  const onAction = () => send(presenting ? {type: 'mode', mode: 'qa'} : {type: 'toggle_listen'});

  return (
    <WearablesApp>
      <div className="shell">
      <main className={`hud${message.dimmed && !detail ? ' hud--dimmed' : ''}`} aria-live="polite">
        {message.state === 'idle' && (
          <div className={`row${connected ? '' : ' offline'}`}>
            <TextView textStyle={TextStyle.META2} textColor={TextColor.SECONDARY}>
              {connected ? 'READY' : 'OFFLINE'}
            </TextView>
          </div>
        )}

        {message.state === 'listening' && (
          <div className="stack">
            <div className="row">
              <TextView textStyle={TextStyle.META1_EMPHASIZED} textColor={TextColor.ACCENT}>
                LISTENING
              </TextView>
            </div>
            {/* Keeps the end of a long question in view: that's the part still being said. */}
            <TextView textStyle={TextStyle.BODY2} textColor={TextColor.SECONDARY}>
              {(message.partial ?? '').length > MAX_PARTIAL ? `…${(message.partial ?? '').slice(-MAX_PARTIAL)}` : message.partial}
            </TextView>
          </div>
        )}

        {message.state === 'thinking' && (
          <div className="stack">
            <TextView textStyle={TextStyle.META1} textColor={TextColor.SECONDARY} className="clamp3">
              Q. {message.question}
            </TextView>
            <TextView textStyle={TextStyle.BODY2}>A. Good question. Short answer is…</TextView>
          </div>
        )}

        {message.state === 'card' && (
          <div className="stack">
            <TextView textStyle={TextStyle.META1} textColor={TextColor.SECONDARY} className="clamp3">
              Q. {message.question}
            </TextView>
            <div className="answer">
              <TextView textStyle={TextStyle.BODY2_EMPHASIZED}>A. {message.lead}</TextView>
              {(detail ? answerPoints : answerPoints?.slice(0, 2))?.map(point => (
                <TextView key={point} textStyle={TextStyle.BODY2}>
                  {point}
                </TextView>
              ))}
            </div>
            <div className="foot">
              {status && (
                <TextView textStyle={TextStyle.META2} textColor={TextColor.SECONDARY}>
                  {status}
                </TextView>
              )}
              {message.source && (
                <div className="row source">
                  <TextView textStyle={TextStyle.META1} textColor={TextColor.ACCENT}>
                    {message.source}
                  </TextView>
                </div>
              )}
            </div>
          </div>
        )}

        {message.state === 'repeat' && (
          <div className="stack">
            <TextView textStyle={TextStyle.BODY2_EMPHASIZED}>Ask to repeat</TextView>
            {message.partial && (
              <TextView textStyle={TextStyle.BODY2} textColor={TextColor.SECONDARY}>
                “{message.partial}”
              </TextView>
            )}
          </div>
        )}

        {message.state === 'present' && (
          <div className="stack">
            <div className="foot">
              <TextView textStyle={TextStyle.META1} textColor={TextColor.SECONDARY}>
                {`${message.page}/${message.total}`}
              </TextView>
              {message.ends_at && (
                <TextView textStyle={TextStyle.META1} textColor={message.behind ? TextColor.ACCENT : TextColor.SECONDARY}>
                  {`${clock(message.ends_at - now)} left`}
                </TextView>
              )}
            </div>
            <TextView textStyle={TextStyle.META1_EMPHASIZED}>{message.title}</TextView>
            {message.behind && (
              <TextView textStyle={TextStyle.META2} textColor={TextColor.ACCENT}>
                {`SPEED UP · ${message.pages_left} TO GO`}
              </TextView>
            )}
            {message.short && (
              <TextView textStyle={TextStyle.BODY2} textColor={TextColor.ACCENT}>
                {message.short}
              </TextView>
            )}
            {!message.short &&
              cuePoints?.map(point => (
                <div key={point.text} className={`row${point.done ? ' done' : ''}`}>
                  <TextView textStyle={TextStyle.BODY2} textColor={point.done ? TextColor.SECONDARY : TextColor.PRIMARY}>
                    {point.text}
                  </TextView>
                </div>
              ))}
          </div>
        )}

        {message.state === 'missed' && (
          <div className="stack">
            <div className="row">
              <TextView textStyle={TextStyle.META1_EMPHASIZED} textColor={TextColor.ACCENT}>
                SKIPPED
              </TextView>
            </div>
            {message.missed?.map(point => (
              <TextView key={point} textStyle={TextStyle.BODY2_EMPHASIZED}>
                {point}
              </TextView>
            ))}
            <TextView textStyle={TextStyle.META1} textColor={TextColor.SECONDARY}>
              {`Now ${message.page}/${message.total}`}
            </TextView>
          </div>
        )}
      </main>
      <div className="dock">
        <ButtonRail>
          <Button title={action} onClick={onAction} />
        </ButtonRail>
      </div>
      </div>
    </WearablesApp>
  );
}
