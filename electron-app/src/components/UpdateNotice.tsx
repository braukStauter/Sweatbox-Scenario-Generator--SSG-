import { useEffect, useState } from 'react';

interface UpdateInfo {
  latestVersion: string;
  currentVersion: string;
  releaseUrl: string;
}

export function UpdateNotice() {
  const [info, setInfo] = useState<UpdateInfo | null>(null);
  const [dismissed, setDismissed] = useState(false);

  useEffect(() => {
    let cancelled = false;
    window.ssg.app
      .checkForUpdates()
      .then(res => {
        if (cancelled) return;
        if (!res.updateAvailable || !res.latestVersion) return;
        setInfo({
          latestVersion: res.latestVersion,
          currentVersion: res.currentVersion,
          releaseUrl: res.releaseUrl,
        });
      })
      .catch(() => {
        /* silent: a failed check shouldn't block the app */
      });
    return () => {
      cancelled = true;
    };
  }, []);

  if (!info || dismissed) return null;

  return (
    <div
      style={{
        background: 'var(--accent, #3b82f6)',
        color: '#fff',
        padding: '8px 14px',
        fontSize: 13,
        borderRadius: 'var(--radius, 6px)',
        marginBottom: 12,
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'space-between',
        gap: 12,
      }}
    >
      <span>
        A new version (<strong>{info.latestVersion}</strong>) is available.
        You are running {info.currentVersion}.
      </span>
      <div style={{ display: 'flex', gap: 8 }}>
        <button
          type="button"
          onClick={() => window.ssg.app.openExternal(info.releaseUrl)}
          style={{
            background: 'rgba(255,255,255,0.18)',
            border: '1px solid rgba(255,255,255,0.45)',
            color: '#fff',
            padding: '4px 10px',
            borderRadius: 4,
            cursor: 'pointer',
            fontSize: 12,
            fontFamily: 'inherit',
          }}
        >
          View release →
        </button>
        <button
          type="button"
          onClick={() => setDismissed(true)}
          aria-label="Dismiss"
          style={{
            background: 'transparent',
            border: '1px solid rgba(255,255,255,0.45)',
            color: '#fff',
            padding: '4px 8px',
            borderRadius: 4,
            cursor: 'pointer',
            fontSize: 12,
            fontFamily: 'inherit',
          }}
        >
          ✕
        </button>
      </div>
    </div>
  );
}
