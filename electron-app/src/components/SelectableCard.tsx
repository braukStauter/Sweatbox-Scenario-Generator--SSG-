import type { PropsWithChildren } from 'react';

interface Props {
  selected: boolean;
  onClick: () => void;
  title: string;
  description?: string;
}

export function SelectableCard({ selected, onClick, title, description }: PropsWithChildren<Props>) {
  return (
    <button
      type="button"
      onClick={onClick}
      style={{
        textAlign: 'left',
        width: '100%',
        background: 'var(--bg-secondary)',
        color: 'var(--fg-primary)',
        border: selected ? '2px solid var(--accent)' : '1px solid var(--border)',
        borderRadius: 'var(--radius)',
        padding: 16,
        cursor: 'pointer',
        fontFamily: 'inherit',
        fontSize: 14,
      }}
      onMouseEnter={e => {
        if (!selected) (e.currentTarget as HTMLButtonElement).style.background = 'var(--bg-tertiary)';
      }}
      onMouseLeave={e => {
        if (!selected) (e.currentTarget as HTMLButtonElement).style.background = 'var(--bg-secondary)';
      }}
    >
      <div style={{ fontWeight: 700, fontSize: 15, marginBottom: description ? 4 : 0 }}>{title}</div>
      {description && (
        <div style={{ color: 'var(--fg-secondary)', fontSize: 12 }}>{description}</div>
      )}
    </button>
  );
}
