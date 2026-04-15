import type { AirportRunwaysEntry } from './types';

/**
 * Parse a config.json airport-group string into row-table entries.
 *
 * Two accepted grammars:
 *
 *   Legacy (runways only, flat-comma):
 *     "KPHX:08,7R,KTUS:12,KABQ:08,03"
 *
 *   Extended (semicolon-separated airports, three colon-fields per airport:
 *     ICAO:runways:STARs, trailing `:` allowed for empty STARs):
 *     "KPHX:08,7R:EAGUL,HYDRR; KTUS:12:; KABQ:08,03:COLTR,BRRTO"
 *
 * The new form is detected by the presence of `;` or `::` in the string.
 * Returned rows always include the `arrivals` field (possibly empty).
 */
export function parseAirportGroupString(value: string): AirportRunwaysEntry[] {
  if (!value) return [];
  const isExtended = value.includes(';') || value.includes('::');
  const out: Array<{ icao: string; runways: string[]; arrivals: string[] }> = [];

  if (isExtended) {
    for (const chunk of value.split(';').map(s => s.trim()).filter(Boolean)) {
      const parts = chunk.split(':').map(s => s.trim());
      const icao = (parts[0] || '').toUpperCase();
      if (!icao) continue;
      const rwys = (parts[1] || '')
        .split(',')
        .map(s => s.trim().toUpperCase())
        .filter(Boolean);
      const stars = (parts[2] || '')
        .split(',')
        .map(s => s.trim().toUpperCase())
        .filter(Boolean);
      out.push({ icao, runways: rwys, arrivals: stars });
    }
  } else {
    const tokens = value.split(',').map(t => t.trim()).filter(Boolean);
    for (const tok of tokens) {
      if (tok.includes(':')) {
        const [icao, rwy] = tok.split(':', 2).map(x => x.trim().toUpperCase());
        if (icao) out.push({ icao, runways: rwy ? [rwy] : [], arrivals: [] });
      } else if (out.length) {
        out[out.length - 1].runways.push(tok.toUpperCase());
      }
    }
  }

  return out.map(e => ({
    icao: e.icao,
    runways: e.runways.join(', '),
    arrivals: e.arrivals.join(', '),
    count: '',
  }));
}
