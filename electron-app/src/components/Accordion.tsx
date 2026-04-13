export interface AccordionCategory {
  id: string;
  label: string;
}

interface Props {
  categories: AccordionCategory[];
  activeId: string;
  onSelect: (id: string) => void;
}

export function AccordionSidebar({ categories, activeId, onSelect }: Props) {
  return (
    <nav
      style={{
        width: 240,
        flexShrink: 0,
        borderRight: '1px solid var(--border)',
        padding: 16,
      }}
    >
      <h3 style={{ margin: '0 0 12px', fontSize: 13, color: 'var(--fg-secondary)' }}>
        CONFIGURATION
      </h3>
      <div className="stack" style={{ gap: 2 }}>
        {categories.map(c => {
          const active = c.id === activeId;
          return (
            <button
              key={c.id}
              type="button"
              onClick={() => onSelect(c.id)}
              style={{
                textAlign: 'left',
                padding: '10px 12px',
                borderRadius: 'var(--radius)',
                border: 'none',
                background: active ? 'var(--accent)' : 'transparent',
                color: 'var(--fg-primary)',
                fontWeight: active ? 700 : 400,
                fontSize: 13,
                cursor: 'pointer',
                fontFamily: 'inherit',
              }}
              onMouseEnter={e => {
                if (!active) (e.currentTarget as HTMLButtonElement).style.background = 'var(--bg-tertiary)';
              }}
              onMouseLeave={e => {
                if (!active) (e.currentTarget as HTMLButtonElement).style.background = 'transparent';
              }}
            >
              {c.label}
            </button>
          );
        })}
      </div>
    </nav>
  );
}
