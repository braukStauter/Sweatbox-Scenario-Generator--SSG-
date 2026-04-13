import { useEffect, useState } from 'react';
import { useScenarioStore } from '../state/scenarioStore';
import { Card, ThemedButton, ThemedInput } from '../components/Themed';
import { SelectableCard } from '../components/SelectableCard';
import { Header } from '../components/Header';

interface AirportEntry {
  icao: string;
  filename: string;
}

export function AirportSelection() {
  const { config, update, setScreen } = useScenarioStore();
  const [airports, setAirports] = useState<AirportEntry[]>([]);
  const [loading, setLoading] = useState(true);
  const [enroute, setEnroute] = useState(false);
  const [artcc, setArtcc] = useState('');

  useEffect(() => {
    window.ssg.airports.list().then(list => {
      setAirports(list);
      setLoading(false);
      if (list.length === 1) update({ departureAirport: list[0].icao });
    });
  }, [update]);

  const selected = enroute ? '' : config.departureAirport;
  const canContinue = enroute ? artcc.trim().length === 3 : !!selected;

  const onNext = () => {
    if (enroute) {
      update({ departureAirport: artcc.toUpperCase(), scenarioType: 'enroute' });
    }
    setScreen('type');
  };

  return (
    <div
      style={{
        display: 'flex',
        flexDirection: 'column',
        height: 'calc(100vh - 40px)',
      }}
    >
      <Header />
      <Card style={{ flex: 1, minHeight: 0, display: 'flex', flexDirection: 'column' }}>
        <div
          style={{
            display: 'flex',
            flexDirection: 'column',
            flex: 1,
            minHeight: 0,
          }}
        >
          <p style={{ color: 'var(--fg-secondary)', margin: '0 0 16px', flexShrink: 0 }}>
            Choose an airport or create an enroute ARTCC scenario.
          </p>

          {loading && <p>Loading airports…</p>}

          <div
            className="stack"
            style={{ flex: 1, minHeight: 0, overflowY: 'auto', paddingRight: 4, gap: 8 }}
          >
            {airports.map(a => (
              <SelectableCard
                key={a.icao}
                selected={!enroute && selected === a.icao}
                onClick={() => {
                  setEnroute(false);
                  update({ departureAirport: a.icao });
                }}
                title={a.icao}
                description={`Airport data from ${a.filename}`}
              />
            ))}

            <div style={{ height: 1, background: 'var(--divider, #2d2d2d)', margin: '4px 0' }} />

            <SelectableCard
              selected={enroute}
              onClick={() => setEnroute(true)}
              title="Enroute (ARTCC) Scenario"
              description="Create an enroute scenario."
            />

            {enroute && (
              <div className="row" style={{ gap: 8, marginTop: 4 }}>
                <ThemedInput
                  placeholder="ARTCC (e.g. ZAB)"
                  value={artcc}
                  maxLength={3}
                  onChange={e => setArtcc(e.target.value.toUpperCase())}
                  style={{ maxWidth: 180 }}
                />
              </div>
            )}
          </div>

          <div className="row" style={{ marginTop: 16, justifyContent: 'flex-end', flexShrink: 0 }}>
            <ThemedButton disabled={!canContinue} onClick={onNext}>
              Next →
            </ThemedButton>
          </div>
        </div>
      </Card>
    </div>
  );
}
