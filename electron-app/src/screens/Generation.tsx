import { useEffect, useState } from 'react';
import { useScenarioStore } from '../state/scenarioStore';
import { Card, ThemedButton } from '../components/Themed';
import type { ScenarioResult } from '../../shared/types';

type PushState =
  | { kind: 'idle' }
  | { kind: 'pushing' }
  | { kind: 'done'; ok: boolean; message: string };

interface Progress {
  message: string;
  percent: number;
}

export function Generation() {
  const { config, importedScenario, setScreen, reset } = useScenarioStore();
  const [result, setResult] = useState<ScenarioResult | null>(importedScenario);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(!importedScenario);
  const [progress, setProgress] = useState<Progress>({
    message: 'Starting scenario generator…',
    percent: 0,
  });
  const [push, setPush] = useState<PushState>({ kind: 'idle' });
  const isImported = !!importedScenario;

  useEffect(() => {
    // Skip Python generation entirely when the user loaded an existing file.
    if (importedScenario) {
      setResult(importedScenario);
      setLoading(false);
      return;
    }
    let cancelled = false;
    const unsubscribe = window.ssg.scenario.onProgress(ev => {
      if (cancelled) return;
      setProgress({ message: ev.message, percent: ev.percent });
    });
    (async () => {
      try {
        const sum = (d: { easy: number; medium: number; hard: number }) =>
          (d.easy || 0) + (d.medium || 0) + (d.hard || 0);
        const sumCounts = (rows: { count?: number | '' }[]) =>
          rows.reduce((t, a) => t + (Number(a.count) || 0), 0);
        const enroute = config.scenarioType === 'enroute';
        const effective = {
          ...config,
          // Enroute derives totals from per-airport rows; others use the
          // global counters (with difficulty override).
          numDepartures: enroute
            ? sumCounts(config.departureAirports)
            : config.departureDifficulty.enabled
              ? sum(config.departureDifficulty)
              : config.numDepartures,
          numArrivals: enroute
            ? sumCounts(config.arrivalAirports)
            : config.arrivalDifficulty.enabled
              ? sum(config.arrivalDifficulty)
              : config.numArrivals,
          numEnroute: config.enrouteDifficulty.enabled
            ? sum(config.enrouteDifficulty)
            : config.numEnroute,
        };
        const r = await window.ssg.scenario.generate(effective);
        if (!cancelled) setResult(r);
      } catch (e) {
        if (!cancelled) setError(String(e));
      } finally {
        if (!cancelled) setLoading(false);
      }
    })();
    return () => {
      cancelled = true;
      unsubscribe();
    };
  }, [config, importedScenario]);

  return (
    <Card title={isImported ? 'Loaded Scenario' : 'Generated Scenario'}>
      {loading && (
        <div className="stack" style={{ gap: 10 }}>
          <div
            style={{
              display: 'flex',
              justifyContent: 'space-between',
              alignItems: 'baseline',
              fontSize: 13,
              gap: 12,
            }}
          >
            <span>{progress.message}</span>
            <span style={{ color: 'var(--fg-secondary)', fontVariantNumeric: 'tabular-nums' }}>
              {Math.max(1, Math.round(progress.percent))}%
            </span>
          </div>
          <div
            style={{
              width: '100%',
              height: 6,
              background: 'var(--bg-tertiary, #2a2a2a)',
              borderRadius: 3,
              overflow: 'hidden',
            }}
          >
            <div
              style={{
                width: `${Math.max(2, progress.percent)}%`,
                height: '100%',
                background: 'var(--accent, #3b82f6)',
                transition: 'width 0.4s ease',
              }}
            />
          </div>
        </div>
      )}
      {error && <p style={{ color: 'var(--error)' }}>Error: {error}</p>}
      {result && (
        <div className="stack">
          <p style={{ color: 'var(--fg-secondary)' }}>
            {isImported
              ? <>Loaded from <code>{result.filename}</code></>
              : <>
                  {result.aircraftCount}
                  {result.generationStats && result.generationStats.requested_total !== result.aircraftCount
                    ? ` of ${result.generationStats.requested_total}`
                    : ''}
                  {' '}flights — <code>{result.filename}</code>
                </>}
          </p>
          {result.generationStats && (() => {
            const s = result.generationStats;
            const shorts = Object.entries(s.shortfall || {}).filter(([, n]) => n > 0);
            if (shorts.length === 0) return null;
            return (
              <p
                style={{
                  color: 'var(--warning, #c77)',
                  fontSize: 12,
                  margin: 0,
                  padding: '6px 10px',
                  border: '1px solid var(--warning, #c77)',
                  borderRadius: 'var(--radius)',
                }}
              >
                Shortfall: {shorts.map(([k, n]) => `${n} ${k}`).join(', ')} — the
                flight pool didn't have enough matching filed plans to satisfy
                the full request.
              </p>
            );
          })()}
          {result.generationStats?.warnings && result.generationStats.warnings.length > 0 && (
            <div
              style={{
                color: 'var(--warning, #c77)',
                fontSize: 12,
                padding: '6px 10px',
                border: '1px solid var(--warning, #c77)',
                borderRadius: 'var(--radius)',
              }}
            >
              <div style={{ fontWeight: 600, marginBottom: 4 }}>Warnings</div>
              <ul style={{ margin: 0, paddingLeft: 18 }}>
                {result.generationStats.warnings.map((w, i) => (
                  <li key={i}>{w}</li>
                ))}
              </ul>
            </div>
          )}
          {result.generationStats?.notes && result.generationStats.notes.length > 0 && (
            <div
              style={{
                color: 'var(--fg-secondary)',
                fontSize: 12,
                padding: '6px 10px',
                border: '1px solid var(--border)',
                borderRadius: 'var(--radius)',
              }}
            >
              <div style={{ fontWeight: 600, marginBottom: 4 }}>Heads up</div>
              <ul style={{ margin: 0, paddingLeft: 18 }}>
                {result.generationStats.notes.map((n, i) => (
                  <li key={i}>{n}</li>
                ))}
              </ul>
            </div>
          )}
          <pre
            style={{
              background: 'var(--bg-primary)',
              border: '1px solid var(--border)',
              borderRadius: 'var(--radius)',
              padding: 12,
              maxHeight: 420,
              overflow: 'auto',
              fontSize: 12,
            }}
          >
            {result.contents}
          </pre>
          <div className="row" style={{ gap: 8, flexWrap: 'wrap' }}>
            <ThemedButton
              onClick={async () => {
                setPush({ kind: 'pushing' });
                try {
                  const r = await window.ssg.vnas.upload(result.contents);
                  setPush({ kind: 'done', ok: r.ok, message: r.message });
                } catch (e) {
                  setPush({ kind: 'done', ok: false, message: String(e) });
                }
              }}
              disabled={push.kind === 'pushing'}
            >
              {push.kind === 'pushing' ? 'Pushing…' : 'Push to vNAS'}
            </ThemedButton>
            <ThemedButton
              secondary
              onClick={() => window.ssg.fs.saveScenario(result.filename, result.contents)}
            >
              Save…
            </ThemedButton>
            {!isImported && (
              <ThemedButton secondary onClick={() => setScreen('config')}>
                ← Edit Config
              </ThemedButton>
            )}
            <ThemedButton secondary onClick={() => reset()}>
              New Scenario
            </ThemedButton>
          </div>
          {push.kind === 'pushing' && (
            <p style={{ color: 'var(--fg-secondary)' }}>
              A vNAS login window is open. Log in (if needed) and navigate to your scenario —
              the scenario ID will be detected automatically.
            </p>
          )}
          {push.kind === 'done' && (
            <p style={{ color: push.ok ? 'var(--success, #6c6)' : 'var(--error)' }}>
              {push.message}
              {!push.ok && (
                <>
                  {' '}
                  <a
                    href="#"
                    onClick={e => {
                      e.preventDefault();
                      window.ssg.vnas.reset();
                      setPush({ kind: 'idle' });
                    }}
                    style={{ color: 'inherit', textDecoration: 'underline' }}
                  >
                    reset vNAS session
                  </a>
                </>
              )}
            </p>
          )}
        </div>
      )}
    </Card>
  );
}
