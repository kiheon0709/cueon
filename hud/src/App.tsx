import {useEffect, useState} from 'react';
import {App as WearablesApp, TextColor, TextStyle, TextView} from '@wearables-ui-toolkit/mrbd';
import {useHub} from './useHub';

// Card dims after this long so the presenter looks back at the audience.
const DIM_AFTER_MS = 10_000;

export default function App() {
  const {message, connected, send} = useHub();
  const [detail, setDetail] = useState(false);
  const [dimmed, setDimmed] = useState(false);

  // New card: reset detail/dim and tell the hub it was rendered (latency log).
  useEffect(() => {
    setDetail(false);
    setDimmed(false);
    if (message.state !== 'card') return;
    send({type: 'rendered', id: message.id});
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
            {(detail ? message.points : message.points?.slice(0, 2))?.map(point => (
              <TextView key={point} textStyle={TextStyle.BODY2}>• {point}</TextView>
            ))}
            {message.source && (
              <TextView textStyle={TextStyle.META1} textColor={TextColor.ACCENT} className="source">
                ▸ {message.source}
              </TextView>
            )}
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
      </main>
    </WearablesApp>
  );
}
