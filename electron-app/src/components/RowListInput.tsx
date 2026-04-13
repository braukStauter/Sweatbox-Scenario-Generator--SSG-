import type { CSSProperties } from 'react';
import { ThemedButton, ThemedInput } from './Themed';

/**
 * Generic tabular "add-row" editor. Replaces comma/semicolon-separated string
 * inputs with an explicit list of rows, each having one or more typed cells.
 *
 * Two shapes:
 *   - `RowListInput<string>` — one column per row (plain list of strings).
 *   - `RowListInput<T extends object>` — multiple columns defined by `columns`.
 */
export interface ColumnDef<T> {
  key: keyof T & string;
  label: string;
  placeholder?: string;
  type?: 'text' | 'number';
  /** Optional flex-basis for the column. Defaults to 140px. */
  flexBasis?: string;
  /** Transform the raw input string before storing. Defaults to identity. */
  parse?: (raw: string) => unknown;
}

interface BaseProps {
  label?: string;
  addLabel?: string;
  emptyHint?: string;
  /** Compact style: single row, no per-field label headers. Used for simple lists. */
  compact?: boolean;
}

interface ObjectProps<T extends object> extends BaseProps {
  mode: 'object';
  value: T[];
  onChange: (next: T[]) => void;
  columns: ColumnDef<T>[];
  /** Factory for a blank row. */
  newRow: () => T;
}

interface StringProps extends BaseProps {
  mode: 'string';
  value: string[];
  onChange: (next: string[]) => void;
  placeholder?: string;
}

type Props<T extends object = object> = StringProps | ObjectProps<T>;

const ROW_STYLE: CSSProperties = {
  position: 'relative',
  display: 'flex',
  gap: 8,
  alignItems: 'flex-end',
  flexWrap: 'wrap',
  background: 'var(--bg-primary)',
  border: '1px solid var(--border)',
  borderRadius: 'var(--radius)',
  padding: 8,
  paddingRight: 32,
  minWidth: 0,
};

const REMOVE_BUTTON_STYLE: CSSProperties = {
  position: 'absolute',
  top: 4,
  right: 4,
  width: 22,
  height: 22,
  padding: 0,
  lineHeight: '20px',
  fontSize: 14,
  fontWeight: 700,
  border: 'none',
  borderRadius: 4,
  background: 'transparent',
  color: 'var(--error)',
  cursor: 'pointer',
};

export function RowListInput<T extends object>(props: Props<T>) {
  const { label, addLabel = '+ Add Row', emptyHint = 'No entries. Click "Add" to create one.', compact } = props;

  const removeRow = (idx: number) => {
    if (props.mode === 'string') {
      props.onChange(props.value.filter((_, i) => i !== idx));
    } else {
      props.onChange(props.value.filter((_, i) => i !== idx));
    }
  };

  const addRow = () => {
    if (props.mode === 'string') {
      props.onChange([...props.value, '']);
    } else {
      props.onChange([...props.value, props.newRow()]);
    }
  };

  return (
    <div className="stack" style={{ gap: 8 }}>
      {label && (
        <span style={{ fontSize: 12, color: 'var(--fg-secondary)', fontWeight: 600 }}>
          {label}
        </span>
      )}

      {props.value.length === 0 && (
        <p style={{ color: 'var(--fg-disabled)', fontSize: 12, margin: 0 }}>{emptyHint}</p>
      )}

      <div className="stack" style={{ gap: 8 }}>
        {props.mode === 'string'
          ? props.value.map((v, i) => (
              <StringRow
                key={i}
                value={v}
                placeholder={props.placeholder}
                compact={compact}
                onChange={next => {
                  const updated = [...props.value];
                  updated[i] = next;
                  (props as StringProps).onChange(updated);
                }}
                onRemove={() => removeRow(i)}
              />
            ))
          : props.value.map((row, i) => (
              <ObjectRow
                key={i}
                row={row}
                columns={(props as ObjectProps<T>).columns}
                onChange={patch => {
                  const updated = [...props.value];
                  updated[i] = { ...updated[i], ...patch };
                  (props as ObjectProps<T>).onChange(updated);
                }}
                onRemove={() => removeRow(i)}
              />
            ))}
      </div>

      <div>
        <ThemedButton secondary onClick={addRow}>
          {addLabel}
        </ThemedButton>
      </div>
    </div>
  );
}

function RemoveButton({ onRemove }: { onRemove: () => void }) {
  return (
    <button
      type="button"
      onClick={onRemove}
      title="Remove row"
      aria-label="Remove row"
      style={REMOVE_BUTTON_STYLE}
      onMouseEnter={e => {
        (e.currentTarget as HTMLButtonElement).style.background = 'var(--error)';
        (e.currentTarget as HTMLButtonElement).style.color = '#fff';
      }}
      onMouseLeave={e => {
        (e.currentTarget as HTMLButtonElement).style.background = 'transparent';
        (e.currentTarget as HTMLButtonElement).style.color = 'var(--error)';
      }}
    >
      ×
    </button>
  );
}

function StringRow({
  value,
  placeholder,
  compact,
  onChange,
  onRemove,
}: {
  value: string;
  placeholder?: string;
  compact?: boolean;
  onChange: (v: string) => void;
  onRemove: () => void;
}) {
  if (compact) {
    return (
      <div style={{ display: 'flex', gap: 4, alignItems: 'center' }}>
        <ThemedInput
          value={value}
          placeholder={placeholder}
          onChange={e => onChange(e.target.value)}
          style={{ flex: 1 }}
        />
        <button
          type="button"
          onClick={onRemove}
          title="Remove"
          aria-label="Remove row"
          style={{
            ...REMOVE_BUTTON_STYLE,
            position: 'relative',
            top: 0,
            right: 0,
          }}
          onMouseEnter={e => {
            (e.currentTarget as HTMLButtonElement).style.background = 'var(--error)';
            (e.currentTarget as HTMLButtonElement).style.color = '#fff';
          }}
          onMouseLeave={e => {
            (e.currentTarget as HTMLButtonElement).style.background = 'transparent';
            (e.currentTarget as HTMLButtonElement).style.color = 'var(--error)';
          }}
        >
          ×
        </button>
      </div>
    );
  }
  return (
    <div style={ROW_STYLE}>
      <RemoveButton onRemove={onRemove} />
      <ThemedInput
        value={value}
        placeholder={placeholder}
        onChange={e => onChange(e.target.value)}
        style={{ flex: 1 }}
      />
    </div>
  );
}

function ObjectRow<T extends object>({
  row,
  columns,
  onChange,
  onRemove,
}: {
  row: T;
  columns: ColumnDef<T>[];
  onChange: (patch: Partial<T>) => void;
  onRemove: () => void;
}) {
  return (
    <div style={ROW_STYLE}>
      <RemoveButton onRemove={onRemove} />
      {columns.map(col => {
        const v = row[col.key];
        const display = v === undefined || v === null ? '' : String(v);
        return (
          <label
            key={col.key}
            className="stack"
            style={{ gap: 4, minWidth: 0, flex: `1 1 ${col.flexBasis ?? '140px'}` }}
          >
            <span style={{ fontSize: 11, color: 'var(--fg-secondary)' }}>{col.label}</span>
            <ThemedInput
              type={col.type ?? 'text'}
              placeholder={col.placeholder}
              value={display}
              onChange={e => {
                const raw = e.target.value;
                const parsed = col.parse
                  ? col.parse(raw)
                  : col.type === 'number'
                    ? raw === '' ? '' : Number(raw)
                    : raw;
                onChange({ [col.key]: parsed } as Partial<T>);
              }}
              style={{ width: '100%' }}
            />
          </label>
        );
      })}
    </div>
  );
}
