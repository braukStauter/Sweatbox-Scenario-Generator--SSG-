import type { WakeBias, WakeCat } from '../../shared/types';
import { adjustBias, biasSum, WAKE_CATS } from '../../shared/wakeBias';
import { ThemedInput } from './Themed';

const LABELS: Record<WakeCat, string> = {
  L: 'Light',
  M: 'Medium',
  H: 'Heavy',
};

const COLORS: Record<WakeCat, string> = {
  L: '#5bc0de',
  M: '#f0ad4e',
  H: '#d9534f',
};

interface Props {
  enabled: boolean;
  bias: WakeBias;
  onEnabledChange: (v: boolean) => void;
  onBiasChange: (b: WakeBias) => void;
}

export function WakeCategoryBias({ enabled, bias, onEnabledChange, onBiasChange }: Props) {
  const sum = biasSum(bias);
  const sumOk = sum === 100;

  const handleChange = (cat: WakeCat, raw: string) => {
    const n = Number(raw);
    if (Number.isNaN(n)) return;
    onBiasChange(adjustBias(bias, cat, n));
  };

  return (
    <div
      className="stack"
      style={{
        border: '1px solid var(--border)',
        borderRadius: 'var(--radius)',
        padding: 12,
        opacity: enabled ? 1 : 0.55,
      }}
    >
      <label className="row" style={{ gap: 8, cursor: 'pointer', userSelect: 'none' }}>
        <input
          type="checkbox"
          checked={enabled}
          onChange={e => onEnabledChange(e.target.checked)}
        />
        <strong>Wake Category Bias</strong>
        <span style={{ color: 'var(--fg-secondary)', fontSize: 12 }}>
          (L/M/H percentage split, sum = 100)
        </span>
      </label>

      <div className="row" style={{ gap: 16 }}>
        {WAKE_CATS.map(cat => (
          <div key={cat} className="stack" style={{ gap: 4, minWidth: 100 }}>
            <label style={{ fontSize: 12, color: COLORS[cat], fontWeight: 700 }}>
              {cat} — {LABELS[cat]}
            </label>
            <div className="row" style={{ gap: 4 }}>
              <ThemedInput
                type="number"
                min={0}
                max={100}
                step={1}
                disabled={!enabled}
                value={bias[cat]}
                onChange={e => handleChange(cat, e.target.value)}
                style={{ width: 72 }}
              />
              <span style={{ color: 'var(--fg-secondary)' }}>%</span>
            </div>
          </div>
        ))}
      </div>

      <div
        style={{
          height: 10,
          display: 'flex',
          borderRadius: 4,
          overflow: 'hidden',
          background: 'var(--bg-tertiary)',
        }}
      >
        {WAKE_CATS.map(cat => (
          <div
            key={cat}
            title={`${cat}: ${bias[cat]}%`}
            style={{ width: `${bias[cat]}%`, background: COLORS[cat] }}
          />
        ))}
      </div>

      <div style={{ fontSize: 12, color: sumOk ? 'var(--success)' : 'var(--error)' }}>
        Sum: {sum}% {sumOk ? '✓' : '— must equal 100'}
      </div>
    </div>
  );
}
