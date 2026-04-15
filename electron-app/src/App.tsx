import { useState } from 'react';
import { useScenarioStore } from './state/scenarioStore';
import { AirportSelection } from './screens/AirportSelection';
import { ScenarioTypeSelection } from './screens/ScenarioTypeSelection';
import { ScenarioConfig } from './screens/ScenarioConfig';
import { Generation } from './screens/Generation';
import { SplashScreen } from './screens/SplashScreen';
import { UpdateNotice } from './components/UpdateNotice';

export function App() {
  const screen = useScenarioStore(s => s.screen);
  const [splashed, setSplashed] = useState(false);

  if (!splashed) return <SplashScreen onComplete={() => setSplashed(true)} />;

  return (
    <div style={{ minHeight: '100vh', padding: '16px 24px 24px' }}>
      <UpdateNotice />
      {screen === 'airport' && <AirportSelection />}
      {screen === 'type' && <ScenarioTypeSelection />}
      {screen === 'config' && <ScenarioConfig />}
      {screen === 'generation' && <Generation />}
    </div>
  );
}
