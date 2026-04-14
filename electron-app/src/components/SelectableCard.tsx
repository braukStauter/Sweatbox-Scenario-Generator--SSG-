import type { PropsWithChildren, KeyboardEvent } from 'react';

interface Props {
  selected: boolean;
  onClick: () => void;
  title: string;
  description?: string;
}

export function SelectableCard({
  selected,
  onClick,
  title,
  description,
  children,
}: PropsWithChildren<Props>) {
  const handleKey = (e: KeyboardEvent<HTMLDivElement>) => {
    if (e.target !== e.currentTarget) return;
    if (e.key === 'Enter' || e.key === ' ') {
      e.preventDefault();
      onClick();
    }
  };

  return (
    <div
      role="button"
      tabIndex={0}
      onClick={onClick}
      onKeyDown={handleKey}
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
        boxSizing: 'border-box',
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'space-between',
        gap: 12,
      }}
      onMouseEnter={e => {
        if (!selected) (e.currentTarget as HTMLDivElement).style.background = 'var(--bg-tertiary)';
      }}
      onMouseLeave={e => {
        if (!selected) (e.currentTarget as HTMLDivElement).style.background = 'var(--bg-secondary)';
      }}
    >
      <div style={{ flex: 1, minWidth: 0 }}>
        <div style={{ fontWeight: 700, fontSize: 15, marginBottom: description ? 4 : 0 }}>
          {title}
        </div>
        {description && (
          <div style={{ color: 'var(--fg-secondary)', fontSize: 12 }}>{description}</div>
        )}
      </div>
      {children && (
        <div
          // Stop clicks/keys inside the embedded content from bubbling up
          // to the card's onClick (which would re-trigger selection or steal
          // focus from inputs).
          onClick={e => e.stopPropagation()}
          onKeyDown={e => e.stopPropagation()}
          style={{ flexShrink: 0 }}
        >
          {children}
        </div>
      )}
    </div>
  );
}
