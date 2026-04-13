import { useScenarioStore } from '../state/scenarioStore';
import { Section } from '../components/Themed';

export function OutputExportSection() {
  const { config } = useScenarioStore();
  const code = (config.departureAirport || 'SCENARIO').replace(/^K/, '');
  return (
    <Section title="Output & Export">
      <p style={{ color: 'var(--fg-secondary)', margin: 0, fontSize: 13 }}>
        Output filename is automatically generated based on airport code.
      </p>
      <code
        style={{
          display: 'inline-block',
          background: 'var(--bg-primary)',
          border: '1px solid var(--border)',
          borderRadius: 'var(--radius)',
          padding: '6px 10px',
          fontSize: 13,
        }}
      >
        {code}_DDHHMM.json
      </code>
    </Section>
  );
}
