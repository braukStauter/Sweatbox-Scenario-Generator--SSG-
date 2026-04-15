import { spawn } from 'node:child_process';
import * as path from 'node:path';
import * as fs from 'node:fs/promises';
import * as fsSync from 'node:fs';
import * as os from 'node:os';
import { app } from 'electron';
import type { ScenarioConfig, ScenarioResult } from '../../shared/types';

interface GenerationStats {
  requested_total: number;
  actual_total: number;
  requested: Record<string, number>;
  actual: Record<string, number>;
  shortfall: Record<string, number>;
}
interface BridgeOk {
  status: 'ok';
  filename: string;
  aircraft_count: number;
  generation_stats?: GenerationStats;
}
interface BridgeErr {
  status: 'error';
  message: string;
  trace?: string;
}
type BridgeResponse = BridgeOk | BridgeErr;

export interface ProgressEvent {
  stage: string;
  message: string;
  percent: number;
}

export type ProgressCallback = (ev: ProgressEvent) => void;

// Ordered list of stage patterns matched against Python's stderr log lines.
// Percents are monotonically increasing — an out-of-order match (e.g., a
// later top-up log arrives after "Generated X aircraft") won't regress the
// bar.
const STAGES: Array<{
  re: RegExp;
  stage: string;
  percent: number;
  label: (m: RegExpMatchArray) => string;
}> = [
  { re: /SSG bridge start/i, stage: 'init', percent: 2, label: () => 'Starting scenario generator…' },
  { re: /Generating ARTCC .* scenario/i, stage: 'init', percent: 5, label: () => 'Initializing ARTCC scenario…' },
  { re: /Fetching Departures Pool/i, stage: 'fetch_dep', percent: 12, label: () => 'Fetching departure flight pool…' },
  { re: /Fetching Arrivals Pool/i, stage: 'fetch_arr', percent: 18, label: () => 'Fetching arrival flight pool…' },
  { re: /Fetching Transient Pool/i, stage: 'fetch_enr', percent: 24, label: () => 'Fetching enroute flight pool…' },
  { re: /Departures Pool:\s*(\d+)/i, stage: 'pool_dep', percent: 32, label: m => `Departures pool loaded (${m[1]} flights)` },
  { re: /Arrivals Pool:\s*(\d+)/i, stage: 'pool_arr', percent: 38, label: m => `Arrivals pool loaded (${m[1]} flights)` },
  { re: /Transient Pool:\s*(\d+)/i, stage: 'pool_enr', percent: 44, label: m => `Enroute pool loaded (${m[1]} flights)` },
  { re: /Generating (\d+) departure aircraft/i, stage: 'gen_dep', percent: 55, label: m => `Generating ${m[1]} departures…` },
  { re: /Generating (\d+) arrival aircraft/i, stage: 'gen_arr', percent: 65, label: m => `Generating ${m[1]} arrivals…` },
  { re: /Generating (\d+) enroute aircraft/i, stage: 'gen_enr', percent: 72, label: m => `Generating ${m[1]} enroute aircraft…` },
  { re: /Generating (\d+) overflight aircraft/i, stage: 'gen_ovf', percent: 78, label: m => `Generating ${m[1]} overflights…` },
  { re: /Top-up pass (\d+)/i, stage: 'topup', percent: 85, label: m => `Top-up pass ${m[1]} — filling shortfall…` },
  { re: /Generation (?:met|shortfall)/i, stage: 'gen_done', percent: 92, label: () => 'Finalizing aircraft list…' },
  { re: /Generated \d+ aircraft/i, stage: 'write', percent: 98, label: () => 'Writing scenario file…' },
];

function resolveBridgeCommand(): { cmd: string; args: string[]; cwd: string } {
  if (app.isPackaged) {
    const exeName = process.platform === 'win32' ? 'ssg_bridge.exe' : 'ssg_bridge';
    const exe = path.join(process.resourcesPath, 'bridge', exeName);
    return { cmd: exe, args: [], cwd: path.dirname(exe) };
  }

  const repoRoot = path.resolve(__dirname, '..', '..', '..', '..');
  const devExe = path.join(repoRoot, 'dist', 'ssg_bridge.exe');
  if (fsSync.existsSync(devExe)) {
    return { cmd: devExe, args: [], cwd: repoRoot };
  }
  const python = process.env.SSG_PYTHON || (process.platform === 'win32' ? 'python' : 'python3');
  return { cmd: python, args: [path.join(repoRoot, 'ssg_bridge.py')], cwd: repoRoot };
}

async function runBridge(
  configPath: string,
  onProgress?: ProgressCallback,
): Promise<BridgeResponse> {
  const { cmd, args, cwd } = resolveBridgeCommand();
  return new Promise((resolve, reject) => {
    const proc = spawn(cmd, [...args, configPath], {
      cwd,
      env: { ...process.env, PYTHONIOENCODING: 'utf-8' },
    });
    let stdout = '';
    let stderr = '';
    let stderrBuf = '';
    let maxPercent = 0;

    const emitFromLine = (line: string) => {
      if (!onProgress || !line) return;
      for (const s of STAGES) {
        const m = line.match(s.re);
        if (!m) continue;
        if (s.percent >= maxPercent) {
          maxPercent = s.percent;
          onProgress({ stage: s.stage, message: s.label(m), percent: s.percent });
        }
        return;
      }
    };

    proc.stdout.on('data', d => (stdout += d.toString()));
    proc.stderr.on('data', d => {
      const text = d.toString();
      stderr += text;
      stderrBuf += text;
      const lines = stderrBuf.split(/\r?\n/);
      stderrBuf = lines.pop() ?? '';
      for (const line of lines) emitFromLine(line);
    });
    proc.on('error', reject);
    proc.on('close', code => {
      if (stderrBuf) emitFromLine(stderrBuf);
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

export async function generateScenario(
  config: ScenarioConfig,
  onProgress?: ProgressCallback,
): Promise<ScenarioResult> {
  const outputDir = path.join(app.getPath('userData'), 'scenarios');
  await fs.mkdir(outputDir, { recursive: true });
  const payload = { ...config, outputDir };
  const tmpFile = path.join(os.tmpdir(), `ssg-cfg-${Date.now()}.json`);
  await fs.writeFile(tmpFile, JSON.stringify(payload, null, 2), 'utf8');

  try {
    const result = await runBridge(tmpFile, onProgress);
    if (result.status === 'error') {
      throw new Error(result.message);
    }
    const contents = await fs.readFile(result.filename, 'utf8');
    onProgress?.({ stage: 'done', message: 'Scenario ready.', percent: 100 });
    return {
      filename: path.basename(result.filename),
      contents,
      flightsUsed: [],
      aircraftCount: result.aircraft_count ?? 0,
      generationStats: result.generation_stats,
    };
  } finally {
    fs.unlink(tmpFile).catch(() => {});
  }
}
