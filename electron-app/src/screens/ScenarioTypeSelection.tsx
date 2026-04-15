import { useScenarioStore } from '../state/scenarioStore';
import { Card, ThemedButton } from '../components/Themed';
import { SelectableCard } from '../components/SelectableCard';
import type { ScenarioType } from '../../shared/types';

const AIRPORT_TYPES: Array<{ id: ScenarioType; title: string; description: string }> = [
  { id: 'ground_departures', title: 'Ground (Departures)', description: 'Departures at parking only.' },
  { id: 'ground_mixed', title: 'Ground (Departures/Arrivals)', description: 'Departures at parking plus arrivals on final.' },
  { id: 'tower_mixed', title: 'Tower (Departures/Arrivals)', description: 'Tower position mixed traffic.' },
  { id: 'tracon_arrivals', title: 'TRACON (Arrivals)', description: 'Arrivals at waypoints on approach.' },
  { id: 'tracon_mixed', title: 'TRACON (Departures/Arrivals)', description: 'TRACON mixed departures and arrivals.' },
];

const ENROUTE_TYPES: Array<{ id: ScenarioType; title: string; description: string }> = [
  { id: 'enroute', title: 'Enroute (ARTCC)', description: 'ARTCC-wide enroute traffic.' },
];

export function ScenarioTypeSelection() {
  const { config, update, setScreen, setImportedScenario } = useScenarioStore();
  const isEnroute = config.scenarioType === 'enroute';
  const list = isEnroute ? ENROUTE_TYPES : AIRPORT_TYPES;

  const chooseJson = async () => {
    const picked = await window.ssg.fs.openScenario();
    if (!picked) return;
    // Validate it parses as JSON before skipping the config flow.
    try {
      JSON.parse(picked.contents);
    } catch (e) {
      alert(`Selected file is not valid JSON: ${String(e)}`);
      return;
    }
    setImportedScenario({
      filename: picked.filename,
      contents: picked.contents,
      flightsUsed: [],
      aircraftCount: 0,
      generationStats: undefined,
    });
    setScreen('generation');
  };

  return (
    <Card title="Select Scenario Type">
      <p style={{ color: 'var(--fg-secondary)', margin: '0 0 16px' }}>
        Choose the type of scenario you want to generate, or load a previously
        generated scenario file to push straight to vNAS.
      </p>
      <div className="stack" style={{ gap: 8 }}>
        {list.map(t => (
          <SelectableCard
            key={t.id}
            selected={config.scenarioType === t.id}
            onClick={() => update({ scenarioType: t.id })}
            title={t.title}
            description={t.description}
          />
        ))}
      </div>
      <div className="row" style={{ marginTop: 16, gap: 8, justifyContent: 'space-between' }}>
        <ThemedButton secondary onClick={() => setScreen('airport')}>← Back</ThemedButton>
        <div className="row" style={{ gap: 8 }}>
          <ThemedButton secondary onClick={chooseJson}>Choose JSON…</ThemedButton>
          <ThemedButton onClick={() => setScreen('config')}>Next →</ThemedButton>
        </div>
      </div>
    </Card>
  );
}
