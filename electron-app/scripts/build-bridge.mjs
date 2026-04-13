#!/usr/bin/env node
/**
 * Build a standalone ssg_bridge.exe via PyInstaller, invoking the host
 * Python only at BUILD time (not at runtime). PyInstaller must be installed
 * in the Python environment used here:
 *
 *     pip install pyinstaller
 *     pip install -r requirements.txt
 *
 * Output:  <repo-root>/dist/ssg_bridge.exe
 */
import { spawn } from 'node:child_process';
import { existsSync } from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const repoRoot = path.resolve(__dirname, '..', '..');
const spec = path.join(repoRoot, 'ssg_bridge.spec');
const python = process.env.SSG_PYTHON || (process.platform === 'win32' ? 'python' : 'python3');

if (!existsSync(spec)) {
  console.error(`[build-bridge] missing spec: ${spec}`);
  process.exit(1);
}

console.log(`[build-bridge] building ssg_bridge via PyInstaller (spec: ${spec})`);

const proc = spawn(python, ['-m', 'PyInstaller', spec, '--clean', '--noconfirm'], {
  cwd: repoRoot,
  stdio: 'inherit',
});

proc.on('exit', code => {
  if (code !== 0) {
    console.error(`[build-bridge] PyInstaller exited ${code}`);
    process.exit(code ?? 1);
  }
  const out = path.join(repoRoot, 'dist', process.platform === 'win32' ? 'ssg_bridge.exe' : 'ssg_bridge');
  if (!existsSync(out)) {
    console.error(`[build-bridge] expected output missing: ${out}`);
    process.exit(1);
  }
  console.log(`[build-bridge] done: ${out}`);
});
