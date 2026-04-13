#!/usr/bin/env node
/**
 * Generate build/icon.ico from gui/SSG_Logo.png (or a user-supplied
 * build/icon.png). Runs on every `npm run package`; no-op if the ICO is
 * already up to date.
 */
import { existsSync, mkdirSync, writeFileSync, statSync } from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import pngToIco from 'png-to-ico';

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const appRoot = path.resolve(__dirname, '..');
const repoRoot = path.resolve(appRoot, '..');
const buildDir = path.join(appRoot, 'build');
const icoOut = path.join(buildDir, 'icon.ico');

const candidates = [
  path.join(buildDir, 'icon.png'),
  path.join(appRoot, 'public', 'logo.png'),
  path.join(repoRoot, 'gui', 'SSG_Logo.png'),
];
const source = candidates.find(p => existsSync(p));

if (!source) {
  console.warn('[build-icon] no source PNG found; skipping. Drop one at build/icon.png to enable.');
  process.exit(0);
}

if (existsSync(icoOut) && statSync(icoOut).mtimeMs >= statSync(source).mtimeMs) {
  console.log('[build-icon] icon.ico up to date');
  process.exit(0);
}

mkdirSync(buildDir, { recursive: true });
const buf = await pngToIco(source);
writeFileSync(icoOut, buf);
console.log(`[build-icon] wrote ${icoOut} from ${path.relative(repoRoot, source)}`);
