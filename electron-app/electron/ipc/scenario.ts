import { spawn } from 'node:child_process';
import * as path from 'node:path';
import * as fs from 'node:fs/promises';
import * as fsSync from 'node:fs';
import * as os from 'node:os';
import { app } from 'electron';
import type { ScenarioConfig, ScenarioResult } from '../../shared/types';

interface BridgeOk {
  status: 'ok';
  filename: string;
  aircraft_count: number;
}
interface BridgeErr {
  status: 'error';
  message: string;
  trace?: string;
}
type BridgeResponse = BridgeOk | BridgeErr;

/**
 * Resolve bridge invocation. Packaged builds ship a standalone
 * `ssg_bridge.exe` (PyInstaller onefile) under resources/bridge/. Dev builds
 * fall back to `python ../ssg_bridge.py` so the same code path works without
 * rebuilding the exe.
 */
function resolveBridgeCommand(): { cmd: string; args: string[]; cwd: string } {
  if (app.isPackaged) {
    const exeName = process.platform === 'win32' ? 'ssg_bridge.exe' : 'ssg_bridge';
    const exe = path.join(process.resourcesPath, 'bridge', exeName);
    return { cmd: exe, args: [], cwd: path.dirname(exe) };
  }

  // Dev: look for a prebuilt exe first (fast path once you've run build:bridge),
  // otherwise shell out to the Python source for live-editing.
  const repoRoot = path.resolve(__dirname, '..', '..', '..', '..');
  const devExe = path.join(repoRoot, 'dist', 'ssg_bridge.exe');
  if (fsSync.existsSync(devExe)) {
    return { cmd: devExe, args: [], cwd: repoRoot };
  }
  const python = process.env.SSG_PYTHON || (process.platform === 'win32' ? 'python' : 'python3');
  return { cmd: python, args: [path.join(repoRoot, 'ssg_bridge.py')], cwd: repoRoot };
}

async function runBridge(configPath: string): Promise<BridgeResponse> {
  const { cmd, args, cwd } = resolveBridgeCommand();
  return new Promise((resolve, reject) => {
    const proc = spawn(cmd, [...args, configPath], {
      cwd,
      env: { ...process.env, PYTHONIOENCODING: 'utf-8' },
    });
    let stdout = '';
    let stderr = '';
    proc.stdout.on('data', d => (stdout += d.toString()));
    proc.stderr.on('data', d => (stderr += d.toString()));
    proc.on('error', reject);
    proc.on('close', code => {
      const lastLine = stdout.trim().split(/\r?\n/).pop() ?? '';
      try {
        resolve(JSON.parse(lastLine));
      } catch {
        resolve({
          status: 'error',
          message: `bridge exited ${code}; stdout: ${stdout.slice(-2000)}; stderr: ${stderr.slice(-2000)}`,
        });
      }
    });
  });
}

export async function generateScenario(config: ScenarioConfig): Promise<ScenarioResult> {
  const outputDir = path.join(app.getPath('userData'), 'scenarios');
  await fs.mkdir(outputDir, { recursive: true });
  const payload = { ...config, outputDir };
  const tmpFile = path.join(os.tmpdir(), `ssg-cfg-${Date.now()}.json`);
  await fs.writeFile(tmpFile, JSON.stringify(payload, null, 2), 'utf8');

  try {
    const result = await runBridge(tmpFile);
    if (result.status === 'error') {
      throw new Error(result.message);
    }
    const contents = await fs.readFile(result.filename, 'utf8');
    return {
      filename: path.basename(result.filename),
      contents,
      flightsUsed: [],
    };
  } finally {
    fs.unlink(tmpFile).catch(() => {});
  }
}
