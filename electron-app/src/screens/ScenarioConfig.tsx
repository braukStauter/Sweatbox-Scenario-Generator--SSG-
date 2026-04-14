import { useMemo, useState } from 'react';
import { useScenarioStore } from '../state/scenarioStore';
import { ThemedButton } from '../components/Themed';
import { AccordionSidebar, type AccordionCategory } from '../components/Accordion';
import { AircraftCountsSection } from '../sections/AircraftCountsSection';
import { RunwayAirportSection } from '../sections/RunwayAirportSection';
import { TimingSpawningSection } from '../sections/TimingSpawningSection';
import { ArrivalsApproachSection } from '../sections/ArrivalsApproachSection';
import { DeparturesClimbSection } from '../sections/DeparturesClimbSection';
import { OutputExportSection } from '../sections/OutputExportSection';
import { EnrouteAirportsSection } from '../sections/EnrouteAirportsSection';
import { AdvancedOptionsSection } from '../sections/AdvancedOptionsSection';
import { isBiasValid } from '../../shared/wakeBias';

export function ScenarioConfig() {
  const { config, setScreen } = useScenarioStore();

  const categories = useMemo<AccordionCategory[]>(() => {
    const isEnroute = config.scenarioType === 'enroute';
    const hasDepartures =
      !isEnroute && config.scenarioType !== 'tracon_arrivals';
    const hasArrivals =
      !isEnroute && config.scenarioType !== 'ground_departures';
    const cats: AccordionCategory[] = [
      { id: 'aircraft_traffic', label: isEnroute ? 'ARTCC & Aircraft' : 'Aircraft & Traffic' },
    ];
    if (isEnroute) cats.push({ id: 'enroute_airports', label: 'Airports & Routes' });
    if (!isEnroute) cats.push({ id: 'runway_airport', label: 'Runway & Airport' });
    cats.push({ id: 'timing_spawning', label: 'Timing & Spawning' });
    if (hasArrivals) cats.push({ id: 'arrivals_approach', label: 'Arrivals & Approach' });
    if (hasDepartures) cats.push({ id: 'departures_climb', label: 'Departures & Climb' });
    cats.push({ id: isEnroute ? 'custom_commands' : 'advanced', label: isEnroute ? 'Custom Commands' : 'Advanced Options' });
    cats.push({ id: 'output_export', label: 'Output & Export' });
    return cats;
  }, [config.scenarioType]);

  const [active, setActive] = useState(categories[0].id);
  const activeIdx = categories.findIndex(c => c.id === active);
  const isFirst = activeIdx <= 0;
  const isLast = activeIdx === categories.length - 1;

  const sumDiff = (d: { easy: number; medium: number; hard: number }) =>
    (d.easy || 0) + (d.medium || 0) + (d.hard || 0);

  const isEnroute = config.scenarioType === 'enroute';
  const sumAirportCounts = (list: { count?: number | '' }[]) =>
    list.reduce((t, a) => t + (Number(a.count) || 0), 0);
  // Enroute gets its dep/arr totals from per-airport rows; everything else
  // uses the global numDepartures/numArrivals (possibly overridden by difficulty).
  const effectiveDep = isEnroute
    ? sumAirportCounts(config.departureAirports)
    : config.departureDifficulty.enabled
      ? sumDiff(config.departureDifficulty)
      : config.numDepartures;
  const effectiveArr = isEnroute
    ? sumAirportCounts(config.arrivalAirports)
    : config.arrivalDifficulty.enabled
      ? sumDiff(config.arrivalDifficulty)
      : config.numArrivals;
  const effectiveEnr = config.enrouteDifficulty.enabled
    ? sumDiff(config.enrouteDifficulty)
    : config.numEnroute;

  function validateCategory(id: string): string | null {
    switch (id) {
      case 'aircraft_traffic':
        if (
          effectiveDep <= 0 &&
          effectiveArr <= 0 &&
          effectiveEnr <= 0 &&
          (config.numOverflight || 0) <= 0
        ) {
          return 'At least one aircraft count must be greater than zero.';
        }
        if (config.wakeBiasEnabled && !isBiasValid(config.wakeBias)) {
          return 'Wake category bias must sum to exactly 100%.';
        }
        return null;
      case 'runway_airport':
        if (config.activeRunways.filter(r => r.trim()).length === 0) {
          return 'Active runways is required.';
        }
        return null;
      case 'enroute_airports':
        if (
          config.arrivalAirports.filter(a => a.icao.trim()).length === 0 &&
          config.departureAirports.filter(a => a.icao.trim()).length === 0
        ) {
          return 'At least one arrival or departure airport is required.';
        }
        {
          const missing = config.arrivalAirports
            .filter(a => a.icao.trim())
            .filter(a => !(Number(a.count) > 0));
          if (missing.length > 0) {
            const list = missing.map(a => a.icao.trim().toUpperCase()).join(', ');
            return `Aircraft count is required for each arrival airport (missing: ${list}).`;
          }
        }
        return null;
      case 'timing_spawning':
        if (config.spawnDelayEnabled) {
          if (config.spawnDelayMode === 'incremental' && !config.incrementalDelayValue.trim()) {
            return 'Incremental delay value is required.';
          }
          if (config.spawnDelayMode === 'total' && !(config.totalSessionMinutes > 0)) {
            return 'Total session minutes must be greater than zero.';
          }
        }
        return null;
      case 'arrivals_approach':
        if (effectiveArr <= 0) return null;
        if (
          config.arrivalMode === 'star' &&
          config.arrivalWaypoints.filter(w => w.waypoint.trim() && w.star.trim()).length === 0
        ) {
          return 'Arrival waypoints are required in STAR mode.';
        }
        if (
          config.arrivalMode === 'frd' &&
          config.frd.filter(r => r.point.trim()).length === 0
        ) {
          return 'At least one FRD point is required in FRD mode.';
        }
        return null;
      default:
        return null;
    }
  }

  const currentError = validateCategory(active);
  const canGenerate =
    isLast && categories.every(c => validateCategory(c.id) === null);

  const goPrev = () => {
    if (isFirst) setScreen('type');
    else setActive(categories[activeIdx - 1].id);
  };
  const goNext = () => {
    if (currentError) return;
    setActive(categories[activeIdx + 1].id);
  };

  return (
    <div
      style={{
        display: 'flex',
        height: 'calc(100vh - 120px)',
        border: '1px solid var(--border)',
        borderRadius: 'var(--radius)',
        background: 'var(--bg-secondary)',
        overflow: 'hidden',
      }}
    >
      <AccordionSidebar categories={categories} activeId={active} onSelect={setActive} />
      <div style={{ flex: 1, display: 'flex', flexDirection: 'column', minWidth: 0 }}>
        <header style={{ padding: '16px 24px', borderBottom: '1px solid var(--border)' }}>
          <h2 className="heading" style={{ margin: 0 }}>
            Configure Scenario — {config.departureAirport}
          </h2>
          <p style={{ color: 'var(--fg-secondary)', margin: '4px 0 0', fontSize: 12 }}>
            {config.scenarioType.replace(/_/g, ' ')}
          </p>
        </header>
        <main style={{ flex: 1, overflowY: 'auto', padding: 24 }}>
          {active === 'aircraft_traffic' && <AircraftCountsSection />}
          {active === 'enroute_airports' && <EnrouteAirportsSection />}
          {active === 'runway_airport' && <RunwayAirportSection />}
          {active === 'timing_spawning' && <TimingSpawningSection />}
          {active === 'arrivals_approach' && <ArrivalsApproachSection />}
          {active === 'departures_climb' && <DeparturesClimbSection />}
          {(active === 'advanced' || active === 'custom_commands') && <AdvancedOptionsSection />}
          {active === 'output_export' && <OutputExportSection />}
        </main>
        <footer
          style={{
            padding: '12px 24px',
            borderTop: '1px solid var(--border)',
            display: 'flex',
            justifyContent: 'space-between',
            alignItems: 'center',
            gap: 8,
          }}
        >
          <ThemedButton secondary onClick={goPrev}>
            ← Back
          </ThemedButton>
          {currentError && (
            <span style={{ color: 'var(--error)', fontSize: 12, flex: 1, textAlign: 'center' }}>
              {currentError}
            </span>
          )}
          {isLast ? (
            <ThemedButton disabled={!canGenerate} onClick={() => setScreen('generation')}>
              Generate →
            </ThemedButton>
          ) : (
            <ThemedButton disabled={!!currentError} onClick={goNext}>
              Next →
            </ThemedButton>
          )}
        </footer>
      </div>
    </div>
  );
}
