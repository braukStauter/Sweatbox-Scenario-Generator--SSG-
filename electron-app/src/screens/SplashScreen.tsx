import { useEffect, useState } from 'react';

interface Props {
  onComplete: () => void;
}

const STEPS: Array<{ label: string; progress: number; delayMs: number }> = [
  { label: 'Starting...', progress: 5, delayMs: 150 },
  { label: 'Checking for updates...', progress: 20, delayMs: 350 },
  { label: 'Loading airport data...', progress: 55, delayMs: 400 },
  { label: 'Initializing components...', progress: 85, delayMs: 300 },
  { label: 'Ready!', progress: 100, delayMs: 400 },
];

export function SplashScreen({ onComplete }: Props) {
  const [step, setStep] = useState(0);

  useEffect(() => {
    if (step >= STEPS.length) {
      const t = setTimeout(onComplete, 200);
      return () => clearTimeout(t);
    }
    const t = setTimeout(() => setStep(s => s + 1), STEPS[step].delayMs);
    return () => clearTimeout(t);
  }, [step, onComplete]);

  const current = STEPS[Math.min(step, STEPS.length - 1)];

  return (
    <div
      style={{
        position: 'fixed',
        inset: 0,
        background: 'var(--bg-primary)',
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'center',
        zIndex: 1000,
      }}
    >
      <div
        style={{
          width: 600,
          padding: 32,
          border: '1px solid var(--border)',
          borderRadius: 'var(--radius)',
          background: 'var(--bg-primary)',
          textAlign: 'center',
        }}
      >
        <img
          src="./header.png"
          alt="Sweatbox Scenario Generator"
          style={{ maxWidth: 540, width: '100%', height: 'auto', display: 'block', margin: '0 auto 16px' }}
        />
        <p style={{ color: 'var(--fg-secondary)', margin: '0 0 24px', fontSize: 13 }}>
          vNAS · Creative Shrimp
        </p>
        <p style={{ color: 'var(--fg-secondary)', margin: '0 0 12px', fontSize: 12 }}>
          {current.label}
        </p>
        <div
          style={{
            width: '100%',
            height: 6,
            background: 'var(--bg-secondary)',
            borderRadius: 3,
            overflow: 'hidden',
          }}
        >
          <div
            style={{
              width: `${current.progress}%`,
              height: '100%',
              background: 'var(--accent)',
              transition: 'width 250ms ease-out',
            }}
          />
        </div>
        <p style={{ color: '#404040', margin: '24px 0 0', fontSize: 11 }}>
          Developed by Creative Shrimp™ (Ethan M) for ZAB
        </p>
      </div>
    </div>
  );
}
