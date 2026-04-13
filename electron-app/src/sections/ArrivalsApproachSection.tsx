import { useScenarioStore } from '../state/scenarioStore';
import { Section, ThemedInput } from '../components/Themed';
import { RowListInput, type ColumnDef } from '../components/RowListInput';
import type { FrdEntry, WaypointStarPair } from '../../shared/types';

const STAR_COLUMNS: ColumnDef<WaypointStarPair>[] = [
  { key: 'waypoint', label: 'Waypoint', placeholder: 'EAGUL', flexBasis: '140px' },
  { key: 'star', label: 'STAR', placeholder: 'JESSE3', flexBasis: '140px' },
];

const FRD_COLUMNS: ColumnDef<FrdEntry>[] = [
  { key: 'point', label: 'FRD Point', placeholder: 'HOMRR020003', flexBasis: '170px' },
  { key: 'altitude', label: 'Altitude (ft)', type: 'number', placeholder: '10000', flexBasis: '120px' },
  { key: 'speed', label: 'Speed (kt)', type: 'number', placeholder: '250', flexBasis: '120px' },
  { key: 'initialRoute', label: 'Initial Route', placeholder: 'HOMRR.EAGUL6', flexBasis: '220px' },
];

export function ArrivalsApproachSection() {
  const { config, update } = useScenarioStore();
  const isStar = config.arrivalMode === 'star';
  return (
    <Section title="Arrivals & Approach">
      <div className="row" style={{ gap: 16 }}>
        <label className="row" style={{ gap: 6 }}>
          <input
            type="radio"
            name="arrivalMode"
            checked={isStar}
            onChange={() => update({ arrivalMode: 'star' })}
          />
          STAR Waypoints
        </label>
        <label className="row" style={{ gap: 6 }}>
          <input
            type="radio"
            name="arrivalMode"
            checked={!isStar}
            onChange={() => update({ arrivalMode: 'frd' })}
          />
          FRD Points
        </label>
      </div>

      {isStar ? (
        <RowListInput
          mode="object"
          label="Arrival Waypoints *"
          addLabel="+ Add STAR"
          emptyHint="No STAR entries. Aircraft will spawn 3 NM prior to the chosen fix."
          value={config.arrivalWaypoints}
          onChange={v => update({ arrivalWaypoints: v })}
          columns={STAR_COLUMNS}
          newRow={() => ({ waypoint: '', star: '' })}
        />
      ) : (
        <RowListInput
          mode="object"
          label="FRD Spawn Points"
          addLabel="+ Add FRD"
          emptyHint="No FRD entries."
          value={config.frd}
          onChange={v => update({ frd: v })}
          columns={FRD_COLUMNS}
          newRow={(): FrdEntry => ({ point: '', altitude: '', speed: '', initialRoute: '' })}
        />
      )}

      <label className="row" style={{ gap: 8, cursor: 'pointer', marginTop: 4 }}>
        <input
          type="checkbox"
          checked={config.useCifpSpeeds}
          onChange={e => update({ useCifpSpeeds: e.target.checked })}
        />
        Use CIFP speed restrictions
      </label>

      {(config.scenarioType === 'tower_mixed' || config.scenarioType === 'tracon_mixed') && (
        <div
          className="stack"
          style={{
            border: '1px solid var(--border)',
            borderRadius: 'var(--radius)',
            padding: 12,
            marginTop: 8,
            opacity: config.enableVfr ? 1 : 0.55,
          }}
        >
          <label className="row" style={{ gap: 8, cursor: 'pointer' }}>
            <input
              type="checkbox"
              checked={config.enableVfr}
              onChange={e => update({ enableVfr: e.target.checked })}
            />
            <strong>Dynamic Tower Arrivals (VFR)</strong>
          </label>
          <label className="stack" style={{ gap: 4 }}>
            <span style={{ fontSize: 12, color: 'var(--fg-secondary)' }}>Number of VFR</span>
            <ThemedInput
              type="number"
              min={0}
              disabled={!config.enableVfr}
              value={config.numVfr}
              onChange={e => update({ numVfr: Math.max(0, Number(e.target.value) || 0) })}
              style={{ width: 120 }}
            />
          </label>
          <RowListInput
            mode="string"
            label="VFR Spawn Locations"
            addLabel="+ Add Location"
            emptyHint="No locations — VFR aircraft spawn 8–12 NM random from the airport."
            placeholder="KABQ020010"
            value={config.vfrSpawnLocations}
            onChange={v => update({ vfrSpawnLocations: v })}
          />
        </div>
      )}
    </Section>
  );
}
