import type { AirportRunwaysEntry } from './types';

/**
 * Parse a config.json airport-group string into row-table entries.
 *
 *   "KPHX:08,7R,KTUS:12,KABQ:08,03"
 *     -> [{icao:"KPHX", runways:"08, 7R"}, {icao:"KTUS", runways:"12"},
 *         {icao:"KABQ", runways:"08, 03"}]
 *
 * The grammar is "ICAO:RWY,RWY,ICAO:RWY,RWY,..." — tokens are comma-separated
 * at a single flat level; a token with a colon starts a new airport, and
 * bare tokens append to the previous airport's runway list.
 */
export function parseAirportGroupString(value: string): AirportRunwaysEntry[] {
  if (!value) return [];
  const tokens = value.split(',').map(t => t.trim()).filter(Boolean);
  const out: Array<{ icao: string; runways: string[] }> = [];
  for (const tok of tokens) {
    if (tok.includes(':')) {
      const [icao, rwy] = tok.split(':', 2).map(x => x.trim().toUpperCase());
      if (icao) out.push({ icao, runways: rwy ? [rwy] : [] });
    } else if (out.length) {
      out[out.length - 1].runways.push(tok.toUpperCase());
    }
  }
  return out.map(e => ({
    icao: e.icao,
    runways: e.runways.join(', '),
    count: '',
  }));
}
