import { useScenarioStore } from '../state/scenarioStore';
import { Section, ThemedButton, ThemedInput } from '../components/Themed';
import { RowListInput } from '../components/RowListInput';
import type { PresetCommandRule, PresetGroupType } from '../../shared/types';

const GROUP_TYPES: Array<{ value: PresetGroupType; label: string }> = [
  { value: 'all', label: 'All Aircraft' },
  { value: 'airline', label: 'Airline' },
  { value: 'destination', label: 'Destination' },
  { value: 'origin', label: 'Origin' },
  { value: 'aircraft_type', label: 'Aircraft Type' },
  { value: 'random', label: 'Random' },
  { value: 'departures', label: 'Departures' },
  { value: 'arrivals', label: 'Arrivals' },
  { value: 'parking', label: 'Parking' },
  { value: 'sid', label: 'SID' },
  { value: 'star', label: 'STAR' },
];

function needsValue(t: PresetGroupType): boolean {
  return t !== 'all' && t !== 'random' && t !== 'departures' && t !== 'arrivals';
}

function emptyRule(): PresetCommandRule {
  return { groupType: 'all', groupValue: '', commandTemplate: '' };
}

export function AdvancedOptionsSection() {
  const { config, update } = useScenarioStore();
  const rules = config.presetCommands;
  const isEnroute = config.scenarioType === 'enroute';
  const customBoundary = config.customBoundary ?? { enabled: false, waypoints: [] };

  const updateRule = (idx: number, patch: Partial<PresetCommandRule>) => {
    const next = rules.map((r, i) => (i === idx ? { ...r, ...patch } : r));
    update({ presetCommands: next });
  };
  const addRule = () => update({ presetCommands: [...rules, emptyRule()] });
  const removeRule = (idx: number) =>
    update({ presetCommands: rules.filter((_, i) => i !== idx) });

  return (
    <div className="stack" style={{ gap: 16 }}>
    {isEnroute && (
      <Section title="Custom Scenario Boundary">
        <p style={{ margin: 0, fontSize: 12, color: 'var(--fg-secondary)' }}>
          Override the ARTCC boundary with a polygon built from the listed
          waypoints/navaids (in order). When enabled, every boundary check
          (spawn tolerance, transient in-airspace test, overflight handoff,
          etc.) uses this polygon instead of the sector's ARTCC outline.
          Minimum 4 waypoints.
        </p>
        <label style={{ display: 'flex', gap: 8, alignItems: 'center', fontSize: 13 }}>
          <input
            type="checkbox"
            checked={customBoundary.enabled}
            onChange={e =>
              update({
                customBoundary: { ...customBoundary, enabled: e.target.checked },
              })
            }
          />
          Use custom boundary for this scenario
        </label>
        {customBoundary.enabled && (
          <RowListInput
            mode="string"
            label="Boundary waypoints (in order)"
            placeholder="e.g. CDS"
            value={customBoundary.waypoints}
            onChange={next =>
              update({
                customBoundary: { ...customBoundary, waypoints: next },
              })
            }
            addLabel="+ Add Waypoint"
            emptyHint="No waypoints yet. Add at least 4 to define the polygon."
          />
        )}
        {customBoundary.enabled && customBoundary.waypoints.filter(w => w.trim()).length < 4 && (
          <p style={{ margin: 0, fontSize: 12, color: 'var(--warning, #c77)' }}>
            {customBoundary.waypoints.filter(w => w.trim()).length} of 4 minimum
            waypoints. Add {4 - customBoundary.waypoints.filter(w => w.trim()).length} more to proceed.
          </p>
        )}
      </Section>
    )}
    <Section title="Preset Commands">
      <p style={{ margin: 0, fontSize: 12, color: 'var(--fg-secondary)' }}>
        Attach vNAS commands to matching aircraft. Template supports{' '}
        <code>$aid $type $orig $dest $wake $alt $spd $cidx</code>.
      </p>

      <div className="stack" style={{ gap: 8 }}>
        {rules.length === 0 && (
          <p style={{ color: 'var(--fg-disabled)', fontSize: 12, margin: 0 }}>
            No preset commands. Click “Add” to create one.
          </p>
        )}
        {rules.map((rule, i) => {
          const showValue = needsValue(rule.groupType);
          return (
            <div
              key={i}
              style={{
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
              }}
            >
              <button
                type="button"
                onClick={() => removeRule(i)}
                title="Remove"
                aria-label="Remove rule"
                style={{
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
              <label className="stack" style={{ gap: 4, minWidth: 0, flex: '1 1 140px' }}>
                <span style={{ fontSize: 11, color: 'var(--fg-secondary)' }}>Match</span>
                <select
                  className="themed"
                  style={{ width: '100%' }}
                  value={rule.groupType}
                  onChange={e =>
                    updateRule(i, { groupType: e.target.value as PresetGroupType })
                  }
                >
                  {GROUP_TYPES.map(g => (
                    <option key={g.value} value={g.value}>
                      {g.label}
                    </option>
                  ))}
                </select>
              </label>
              {showValue && (
                <label className="stack" style={{ gap: 4, minWidth: 0, flex: '1 1 140px' }}>
                  <span style={{ fontSize: 11, color: 'var(--fg-secondary)' }}>Value</span>
                  <ThemedInput
                    placeholder="e.g. AAL"
                    value={rule.groupValue}
                    onChange={e => updateRule(i, { groupValue: e.target.value })}
                    style={{ width: '100%' }}
                  />
                </label>
              )}
              <label className="stack" style={{ gap: 4, flex: '2 1 200px', minWidth: 0 }}>
                <span style={{ fontSize: 11, color: 'var(--fg-secondary)' }}>Command</span>
                <ThemedInput
                  placeholder="SAYF THIS IS $aid"
                  value={rule.commandTemplate}
                  onChange={e => updateRule(i, { commandTemplate: e.target.value })}
                  style={{ width: '100%' }}
                />
              </label>
            </div>
          );
        })}
      </div>

      <div>
        <ThemedButton secondary onClick={addRule}>
          + Add Rule
        </ThemedButton>
      </div>
    </Section>
    </div>
  );
}
