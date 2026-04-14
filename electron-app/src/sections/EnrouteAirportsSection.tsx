import { useEffect, useState } from 'react';
import { useScenarioStore } from '../state/scenarioStore';
import { Section, ThemedButton } from '../components/Themed';
import { RowListInput, type ColumnDef } from '../components/RowListInput';
import { parseAirportGroupString } from '../../shared/airportGroups';
import type { AirportRunwaysEntry, SsgConfig } from '../../shared/types';

const DEPARTURE_COLUMNS: ColumnDef<AirportRunwaysEntry>[] = [
  { key: 'icao', label: 'ICAO', placeholder: 'KPHX', flexBasis: '140px' },
  { key: 'runways', label: 'Runways', placeholder: '08, 7R', flexBasis: '220px' },
  { key: 'count', label: 'Aircraft *', type: 'number', placeholder: '5', flexBasis: '90px' },
];

const ARRIVAL_COLUMNS: ColumnDef<AirportRunwaysEntry>[] = [
  { key: 'icao', label: 'ICAO', placeholder: 'KPHX', flexBasis: '140px' },
  { key: 'runways', label: 'Runways', placeholder: '08, 7R', flexBasis: '220px' },
  { key: 'count', label: 'Aircraft *', type: 'number', placeholder: '5', flexBasis: '90px' },
];

/**
 * Read `config.json`'s `artcc_airport_groups.{ARTCC}` and expose a dropdown
 * that pre-fills the airport/runway table with a named group. The user can
 * still edit rows after applying a group. Group names are the keys inside
 * the ARTCC object (e.g. "Primary Airports (East)").
 */
export function EnrouteAirportsSection() {
  const { config, update } = useScenarioStore();
  const [groupConfig, setGroupConfig] = useState<Record<string, string>>({});
  const [selectedGroup, setSelectedGroup] = useState<string>('');

  useEffect(() => {
    let alive = true;
    (async () => {
      const raw = (await window.ssg.fs.loadConfig()) as SsgConfig | null;
      if (!alive) return;
      const artccId = (config.departureAirport || '').toUpperCase();
      const perArtcc = raw?.artcc_airport_groups?.[artccId] || {};
      setGroupConfig(perArtcc);
    })();
    return () => {
      alive = false;
    };
  }, [config.departureAirport]);

  const applyGroup = (direction: 'arrival' | 'departure') => {
    const raw = groupConfig[selectedGroup];
    if (!raw) return;
    const rows = parseAirportGroupString(raw);
    if (direction === 'arrival') update({ arrivalAirports: rows });
    else update({ departureAirports: rows });
  };

  const groupNames = Object.keys(groupConfig);

  return (
    <Section title="Airports & Routes">
      {groupNames.length > 0 && (
        <div
          className="row"
          style={{
            gap: 8,
            alignItems: 'flex-end',
            flexWrap: 'wrap',
            border: '1px solid var(--border)',
            borderRadius: 'var(--radius)',
            padding: 10,
            background: 'var(--bg-primary)',
          }}
        >
          <label className="stack" style={{ gap: 4, flex: '1 1 220px' }}>
            <span style={{ fontSize: 11, color: 'var(--fg-secondary)' }}>
              Predefined airport group for {config.departureAirport}
            </span>
            <select
              className="themed"
              value={selectedGroup}
              onChange={e => setSelectedGroup(e.target.value)}
            >
              <option value="">— select —</option>
              {groupNames.map(n => (
                <option key={n} value={n}>
                  {n}
                </option>
              ))}
            </select>
          </label>
          <ThemedButton
            secondary
            disabled={!selectedGroup}
            onClick={() => applyGroup('arrival')}
          >
            Use for Arrivals
          </ThemedButton>
          <ThemedButton
            secondary
            disabled={!selectedGroup}
            onClick={() => applyGroup('departure')}
          >
            Use for Departures
          </ThemedButton>
        </div>
      )}

      <RowListInput
        mode="object"
        label="Arrival Airports"
        addLabel="+ Add Arrival Airport"
        emptyHint="No arrival airports configured."
        value={config.arrivalAirports}
        onChange={v => update({ arrivalAirports: v })}
        columns={ARRIVAL_COLUMNS}
        newRow={(): AirportRunwaysEntry => ({ icao: '', runways: '', count: '' })}
      />
      <RowListInput
        mode="object"
        label="Departure Airports"
        addLabel="+ Add Departure Airport"
        emptyHint="No departure airports configured."
        value={config.departureAirports}
        onChange={v => update({ departureAirports: v })}
        columns={DEPARTURE_COLUMNS}
        newRow={(): AirportRunwaysEntry => ({ icao: '', runways: '', count: '' })}
      />
      <p style={{ fontSize: 11, color: 'var(--fg-disabled)', margin: 0 }}>
        Aircraft counts here replace the global Arrivals/Departures totals on
        the Aircraft & Traffic page when generating an enroute scenario.
        <br />* required for arrival airports.
      </p>
    </Section>
  );
}
