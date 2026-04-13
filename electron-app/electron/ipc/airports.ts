import * as path from 'node:path';
import * as fs from 'node:fs/promises';
import { app } from 'electron';

export interface AirportEntry {
  icao: string;
  filename: string;
}

/**
 * Return the directory that contains airport_data/.
 *   - Packaged: resources/airport_data (bundled via electron-builder extraResources)
 *   - Dev:      two levels up from electron-app/ (the Python repo root)
 */
function airportDataDir(): string {
  if (app.isPackaged) {
    return path.join(process.resourcesPath, 'airport_data');
  }
  return path.resolve(__dirname, '..', '..', '..', '..', 'airport_data');
}

export async function listAirports(): Promise<AirportEntry[]> {
  const dir = airportDataDir();
  try {
    const files = await fs.readdir(dir);
    return files
      .filter(f => f.toLowerCase().endsWith('.geojson'))
      .map(f => ({ icao: f.replace(/\.geojson$/i, '').toUpperCase(), filename: f }))
      .sort((a, b) => a.icao.localeCompare(b.icao));
  } catch (err) {
    console.error('[airports] listAirports failed', err);
    return [];
  }
}
