import { useState } from 'react';
import { ThemedInput } from './Themed';
import type { GaConfig, GaFlightRules } from '../../shared/types';

interface Props {
  value: GaConfig;
  onChange: (next: GaConfig) => void;
}

/**
 * Collapsible panel embedded in the Aircraft Counts page. When `value.enabled`
 * is false (the default), the scenario skips all GA-tagged parking spots
 * entirely — no airline aircraft are placed on them either. When enabled, the
 * user sets per-direction counts and picks VFR or IFR:
 *   - VFR: aircraft generated from a hardcoded fleet list (C172, SR22, ...)
 *     with synthesized flight plans.
 *   - IFR: picks a flight plan from the main API pool whose aircraftType
 *     matches a GA type (no extra API call).
 */
export function GeneralAviationCounts({ value, onChange }: Props) {
  const [open, setOpen] = useState(value.enabled);

  const update = (patch: Partial<GaConfig>) => onChange({ ...value, ...patch });
  const setDep = (patch: Partial<GaConfig['departures']>) =>
    onChange({ ...value, departures: { ...value.departures, ...patch } });
  const setArr = (patch: Partial<GaConfig['arrivals']>) =>
    onChange({ ...value, arrivals: { ...value.arrivals, ...patch } });

  return (
    <div
      style={{
        border: '1px solid var(--border)',
        borderRadius: 'var(--radius)',
        padding: 12,
        background: 'var(--bg-secondary)',
      }}
    >
      <button
        type="button"
        onClick={() => setOpen(o => !o)}
        aria-expanded={open}
        style={{
          width: '100%',
          textAlign: 'left',
          border: 'none',
          background: 'transparent',
          color: 'var(--fg-primary)',
          fontFamily: 'inherit',
          fontSize: 14,
          fontWeight: 600,
          padding: 0,
          cursor: 'pointer',
          display: 'flex',
          alignItems: 'center',
          gap: 8,
        }}
      >
        <span style={{ color: 'var(--fg-secondary)', width: 12 }}>{open ? '▾' : '▸'}</span>
        General Aviation
        {value.enabled && (
          <span style={{ color: 'var(--fg-secondary)', fontWeight: 400, fontSize: 12 }}>
            ({value.departures.count} dep {value.departures.mode}, {value.arrivals.count} arr {value.arrivals.mode})
          </span>
        )}
      </button>

      {open && (
        <div className="stack" style={{ gap: 12, marginTop: 12 }}>
          <label style={{ display: 'flex', gap: 8, alignItems: 'center' }}>
            <input
              type="checkbox"
              checked={value.enabled}
              onChange={e => update({ enabled: e.target.checked })}
            />
            <span>Include General Aviation traffic</span>
          </label>
          <p style={{ margin: 0, fontSize: 12, color: 'var(--fg-secondary)' }}>
            GA parking spots are skipped unless this is enabled. VFR GA uses a
            hardcoded fleet; IFR GA pulls a flight plan from the main pool
            whose aircraft type matches.
          </p>

          <div
            className="row"
            style={{ gap: 16, flexWrap: 'wrap', opacity: value.enabled ? 1 : 0.5 }}
          >
            <DirectionBlock
              label="Departures"
              count={value.departures.count}
              mode={value.departures.mode}
              disabled={!value.enabled}
              onCount={count => setDep({ count })}
              onMode={mode => setDep({ mode })}
            />
            <DirectionBlock
              label="Arrivals"
              count={value.arrivals.count}
              mode={value.arrivals.mode}
              disabled={!value.enabled}
              onCount={count => setArr({ count })}
              onMode={mode => setArr({ mode })}
            />
          </div>
        </div>
      )}
    </div>
  );
}

function DirectionBlock({
  label,
  count,
  mode,
  disabled,
  onCount,
  onMode,
}: {
  label: string;
  count: number;
  mode: GaFlightRules;
  disabled: boolean;
  onCount: (n: number) => void;
  onMode: (m: GaFlightRules) => void;
}) {
  return (
    <div className="stack" style={{ gap: 6, minWidth: 180 }}>
      <span style={{ fontSize: 12, color: 'var(--fg-secondary)' }}>{label}</span>
      <ThemedInput
        type="number"
        min={0}
        value={count}
        disabled={disabled}
        onChange={e => onCount(Math.max(0, Number(e.target.value) || 0))}
        style={{ width: 100 }}
      />
      <div className="row" style={{ gap: 12 }}>
        {(['VFR', 'IFR'] as const).map(r => (
          <label key={r} style={{ display: 'flex', gap: 4, alignItems: 'center' }}>
            <input
              type="radio"
              name={`${label}-mode`}
              value={r}
              checked={mode === r}
              disabled={disabled}
              onChange={() => onMode(r)}
            />
            <span style={{ fontSize: 13 }}>{r}</span>
          </label>
        ))}
      </div>
    </div>
  );
}
