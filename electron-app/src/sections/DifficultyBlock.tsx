import type { DifficultyCounts } from '../../shared/types';
import { ThemedInput } from '../components/Themed';

interface Props {
  label: string;
  value: DifficultyCounts;
  onChange: (v: DifficultyCounts) => void;
}

const FIELDS: Array<{ key: keyof Omit<DifficultyCounts, 'enabled'>; label: string; color: string }> = [
  { key: 'easy', label: 'Easy', color: 'var(--success)' },
  { key: 'medium', label: 'Medium', color: 'var(--warning)' },
  { key: 'hard', label: 'Hard', color: 'var(--error)' },
];

export function DifficultyBlock({ label, value, onChange }: Props) {
  return (
    <div
      className="stack"
      style={{
        border: '1px solid var(--border)',
        borderRadius: 'var(--radius)',
        padding: 12,
        gap: value.enabled ? 12 : 0,
      }}
    >
      <label className="row" style={{ gap: 8, cursor: 'pointer', userSelect: 'none' }}>
        <input
          type="checkbox"
          checked={value.enabled}
          onChange={e => onChange({ ...value, enabled: e.target.checked })}
        />
        <strong>{label}</strong>
      </label>
      {value.enabled && (
        <div className="row" style={{ gap: 12, flexWrap: 'wrap' }}>
          {FIELDS.map(f => (
            <label key={f.key} className="stack" style={{ gap: 4 }}>
              <span style={{ fontSize: 12, color: f.color, fontWeight: 700 }}>{f.label}</span>
              <ThemedInput
                type="number"
                min={0}
                value={value[f.key]}
                onChange={e => onChange({ ...value, [f.key]: Math.max(0, Number(e.target.value) || 0) })}
                style={{ width: 80 }}
              />
            </label>
          ))}
        </div>
      )}
    </div>
  );
}
