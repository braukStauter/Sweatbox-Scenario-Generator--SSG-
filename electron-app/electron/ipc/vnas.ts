import { BrowserWindow, session } from 'electron';
import type { VNASUploadResult } from '../../shared/types';

const LOGIN_URL = 'https://data-admin.vnas.vatsim.net/training';
const API_BASE = 'https://data-api.vnas.vatsim.net';
const SCENARIO_ID_RE = /\/scenarios\/([a-zA-Z0-9_-]+)/;
const PARTITION = 'persist:vnas';
const LOGIN_TIMEOUT_MS = 5 * 60 * 1000;

interface VNASState {
  window: BrowserWindow | null;
  scenarioId: string | null;
}

const state: VNASState = { window: null, scenarioId: null };

function hasLiveWindow(): boolean {
  return !!state.window && !state.window.isDestroyed();
}

function openLoginWindow(): BrowserWindow {
  const win = new BrowserWindow({
    width: 1200,
    height: 900,
    title: 'vNAS Login — navigate to your scenario',
    autoHideMenuBar: true,
    webPreferences: {
      partition: PARTITION,
      contextIsolation: true,
      nodeIntegration: false,
    },
  });
  win.loadURL(LOGIN_URL);

  // Paint the instruction banner on every page the user lands on within the
  // data-admin frontend *until* they navigate into a specific scenario page
  // (where we hide it to keep the Edit pane unobstructed). Covers the
  // post-login landing, the scenarios list, and any SPA route between.
  const maybeShowInstruction = () => {
    if (win.isDestroyed()) return;
    const url = win.webContents.getURL();
    if (!url || !url.startsWith('https://data-admin.vnas.vatsim.net')) return;
    if (SCENARIO_ID_RE.test(url)) {
      void clearInstruction(win);
    } else {
      void injectInstruction(win);
    }
  };
  win.webContents.on('did-finish-load', maybeShowInstruction);
  win.webContents.on('did-frame-finish-load', maybeShowInstruction);
  win.webContents.on('did-navigate', maybeShowInstruction);
  win.webContents.on('did-navigate-in-page', maybeShowInstruction);

  win.on('closed', () => {
    if (state.window === win) {
      state.window = null;
      state.scenarioId = null;
    }
  });
  return win;
}

async function injectInstruction(win: BrowserWindow): Promise<void> {
  if (win.isDestroyed()) return;
  const js = `
    (() => {
      if (document.getElementById('__ssg_instruction__')) return;
      const el = document.createElement('div');
      el.id = '__ssg_instruction__';
      Object.assign(el.style, {
        position: 'fixed',
        top: '0', left: '0', right: '0',
        zIndex: '2147483646',
        padding: '14px 22px',
        background: 'linear-gradient(135deg, #b46a00, #e38d1a)',
        color: '#ffffff',
        fontFamily: '-apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif',
        fontSize: '14px',
        fontWeight: '600',
        boxShadow: '0 4px 12px rgba(0,0,0,0.35)',
        display: 'flex',
        justifyContent: 'space-between',
        alignItems: 'center',
        gap: '16px',
      });
      const msg = document.createElement('div');
      msg.innerHTML =
        '<span style="margin-right:8px;font-size:16px;">\u26A0\uFE0F</span>' +
        '<strong>SSG:</strong> Click the <strong>EDIT</strong> icon on the scenario ' +
        'you wish to import to. ' +
        '<span style="opacity:0.9;font-weight:400;">' +
        'Warning: this action cannot be undone.</span>';
      const close = document.createElement('button');
      close.textContent = '\u2715';
      Object.assign(close.style, {
        border: 'none', background: 'rgba(0,0,0,0.25)', color: '#ffffff',
        width: '28px', height: '28px', borderRadius: '6px',
        cursor: 'pointer', fontSize: '14px', fontFamily: 'inherit',
      });
      close.title = 'Dismiss';
      close.addEventListener('click', () => el.remove());
      el.appendChild(msg);
      el.appendChild(close);
      document.body.appendChild(el);
      // Nudge page content down so the banner doesn't cover header controls.
      if (!document.body.dataset.ssgBannerPadded) {
        document.body.dataset.ssgBannerPadded = '1';
        document.body.style.paddingTop =
          ((parseInt(getComputedStyle(document.body).paddingTop, 10) || 0) + 60) + 'px';
      }
    })();
  `;
  try {
    await win.webContents.executeJavaScript(js, true);
  } catch (err) {
    console.warn('[vnas] instruction injection failed:', err);
  }
}

async function clearInstruction(win: BrowserWindow): Promise<void> {
  if (win.isDestroyed()) return;
  const js = `
    (() => {
      const el = document.getElementById('__ssg_instruction__');
      if (el) el.remove();
      if (document.body.dataset.ssgBannerPadded) {
        const cur = parseInt(getComputedStyle(document.body).paddingTop, 10) || 0;
        document.body.style.paddingTop = Math.max(0, cur - 60) + 'px';
        delete document.body.dataset.ssgBannerPadded;
      }
    })();
  `;
  try {
    await win.webContents.executeJavaScript(js, true);
  } catch {
    /* benign — page may have navigated */
  }
}

async function waitForScenarioNav(win: BrowserWindow): Promise<string> {
  return new Promise<string>((resolve, reject) => {
    let resolved = false;

    const timer = setTimeout(() => {
      if (resolved) return;
      resolved = true;
      cleanup();
      reject(new Error('Timed out waiting for scenario navigation (5 min).'));
    }, LOGIN_TIMEOUT_MS);

    // data-admin.vnas.vatsim.net is a SPA; some routing changes go through
    // history.pushState without firing `did-navigate*`. Poll the URL as a
    // fallback so we catch those. 250 ms is imperceptible to the user.
    const poll = setInterval(() => {
      if (win.isDestroyed()) return;
      tryMatch(win.webContents.getURL(), 'poll');
    }, 250);

    const tryMatch = (url: string, source: string) => {
      if (resolved || !url) return;
      const m = SCENARIO_ID_RE.exec(url);
      if (m) {
        console.log(`[vnas] matched scenario ${m[1]} via ${source}: ${url}`);
        resolved = true;
        cleanup();
        resolve(m[1]);
      }
    };

    const onNav = (_e: unknown, url: string) => tryMatch(url, 'did-navigate');
    const onNavInPage = (_e: unknown, url: string) => tryMatch(url, 'did-navigate-in-page');
    const onClosed = () => {
      if (resolved) return;
      resolved = true;
      cleanup();
      reject(new Error('Login window closed before a scenario was selected.'));
    };

    function cleanup() {
      clearTimeout(timer);
      clearInterval(poll);
      if (!win.isDestroyed()) {
        win.webContents.removeListener('did-navigate', onNav);
        win.webContents.removeListener('did-navigate-in-page', onNavInPage);
        win.removeListener('closed', onClosed);
      }
    }

    win.webContents.on('did-navigate', onNav);
    win.webContents.on('did-navigate-in-page', onNavInPage);
    win.on('closed', onClosed);

    tryMatch(win.webContents.getURL(), 'initial');
  });
}

async function ensureLogin(): Promise<{ win: BrowserWindow; scenarioId: string }> {
  if (hasLiveWindow() && state.scenarioId) {
    return { win: state.window!, scenarioId: state.scenarioId };
  }
  if (!hasLiveWindow()) {
    state.window = openLoginWindow();
  }
  const win = state.window!;
  win.focus();
  const id = await waitForScenarioNav(win);
  state.scenarioId = id;
  return { win, scenarioId: id };
}

interface FetchOutcome {
  status: number;
  ok: boolean;
  body: string;
}

async function browserFetch(
  win: BrowserWindow,
  url: string,
  init: { method: string; body?: string },
): Promise<FetchOutcome> {
  const bodyLiteral = init.body === undefined ? 'undefined' : JSON.stringify(init.body);
  const js = `
    (async () => {
      try {
        const res = await fetch(${JSON.stringify(url)}, {
          method: ${JSON.stringify(init.method)},
          credentials: 'include',
          headers: {
            'Content-Type': 'application/json',
            'Accept': 'application/json',
          },
          body: ${bodyLiteral},
        });
        const text = await res.text();
        return { status: res.status, ok: res.ok, body: text };
      } catch (err) {
        return { status: 0, ok: false, body: String(err) };
      }
    })()
  `;
  return (await win.webContents.executeJavaScript(js, true)) as FetchOutcome;
}

async function injectSuccessToast(win: BrowserWindow, message: string): Promise<void> {
  if (win.isDestroyed()) return;
  const js = `
    (() => {
      const existing = document.getElementById('__ssg_toast__');
      if (existing) existing.remove();
      const el = document.createElement('div');
      el.id = '__ssg_toast__';
      el.textContent = ${JSON.stringify(message)};
      Object.assign(el.style, {
        position: 'fixed',
        top: '20px',
        left: '50%',
        transform: 'translateX(-50%)',
        zIndex: '2147483647',
        padding: '14px 22px',
        borderRadius: '8px',
        background: 'linear-gradient(135deg, #1f9e4a, #2ec56d)',
        color: '#ffffff',
        fontFamily: '-apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif',
        fontSize: '15px',
        fontWeight: '600',
        boxShadow: '0 10px 30px rgba(0,0,0,0.35)',
        opacity: '0',
        transition: 'opacity 220ms ease, transform 220ms ease',
        pointerEvents: 'auto',
        cursor: 'pointer',
      });
      el.title = 'Click to dismiss';
      el.addEventListener('click', () => el.remove());
      document.body.appendChild(el);
      requestAnimationFrame(() => {
        el.style.opacity = '1';
        el.style.transform = 'translateX(-50%) translateY(4px)';
      });
      setTimeout(() => {
        if (!el.isConnected) return;
        el.style.opacity = '0';
        setTimeout(() => el.remove(), 300);
      }, 6000);
    })();
  `;
  try {
    await win.webContents.executeJavaScript(js, true);
  } catch (err) {
    // The user may have navigated away or closed the window between the PUT
    // succeeding and the toast executing; that's benign.
    console.warn('[vnas] toast injection failed:', err);
  }
}

export async function uploadScenario(scenarioContents: string): Promise<VNASUploadResult> {
  let incoming: { aircraft?: unknown } & Record<string, unknown>;
  try {
    incoming = JSON.parse(scenarioContents);
  } catch (e) {
    return { ok: false, status: 0, message: `Invalid scenario JSON: ${String(e)}` };
  }
  if (!Array.isArray(incoming.aircraft)) {
    return { ok: false, status: 0, message: 'Scenario JSON has no aircraft array.' };
  }

  let win: BrowserWindow;
  let scenarioId: string;
  try {
    ({ win, scenarioId } = await ensureLogin());
  } catch (e) {
    return { ok: false, status: 0, message: String(e instanceof Error ? e.message : e) };
  }

  const endpoint = `${API_BASE}/api/training/scenarios/${scenarioId}`;

  const existing = await browserFetch(win, endpoint, { method: 'GET' });
  let payload: Record<string, unknown>;
  if (existing.ok && existing.body) {
    try {
      const parsed = JSON.parse(existing.body) as Record<string, unknown>;
      parsed.aircraft = incoming.aircraft;
      payload = parsed;
    } catch {
      payload = { ...incoming, id: scenarioId };
    }
  } else if (existing.status === 401) {
    state.scenarioId = null;
    return {
      ok: false,
      status: 401,
      message: 'Authentication expired. Please log in again and retry.',
      scenarioId,
    };
  } else if (existing.status === 404) {
    state.scenarioId = null;
    return {
      ok: false,
      status: 404,
      message: `Scenario ${scenarioId} not found. Navigate to a different scenario and retry.`,
      scenarioId,
    };
  } else {
    payload = { ...incoming, id: scenarioId };
  }

  const put = await browserFetch(win, endpoint, {
    method: 'PUT',
    body: JSON.stringify(payload),
  });

  if (put.status === 200 || put.status === 204) {
    const aircraftCount = (payload.aircraft as unknown[]).length;
    const message = `Pushed ${aircraftCount} aircraft to vNAS.`;
    // Fire-and-forget: overlay a green toast on the vNAS window so the user
    // sees confirmation right where they navigated to the scenario. Failing
    // to inject (window closed, navigation mid-push) is non-fatal.
    void injectSuccessToast(win, `SSG: imported ${aircraftCount} aircraft ✓`);
    return { ok: true, status: put.status, message, scenarioId };
  }
  if (put.status === 401) {
    state.scenarioId = null;
    return { ok: false, status: 401, message: 'Authentication expired. Please log in again.', scenarioId };
  }
  if (put.status === 404) {
    state.scenarioId = null;
    return { ok: false, status: 404, message: `Scenario ${scenarioId} not found.`, scenarioId };
  }
  return {
    ok: false,
    status: put.status,
    message: `Upload failed (status ${put.status}): ${put.body.slice(0, 500)}`,
    scenarioId,
  };
}

export function resetVnasSession(): void {
  state.scenarioId = null;
  if (hasLiveWindow()) {
    state.window!.close();
  }
  state.window = null;
}

export async function clearVnasCookies(): Promise<void> {
  resetVnasSession();
  const s = session.fromPartition(PARTITION);
  await s.clearStorageData({ storages: ['cookies', 'localstorage', 'indexdb'] });
}
