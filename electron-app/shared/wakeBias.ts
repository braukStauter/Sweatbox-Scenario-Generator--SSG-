import type { WakeBias, WakeCat } from './types';

export const WAKE_CATS: readonly WakeCat[] = ['L', 'M', 'H'] as const;

export function defaultBias(): WakeBias {
  return { L: 33, M: 34, H: 33 };
}

export function biasSum(b: WakeBias): number {
  return b.L + b.M + b.H;
}

export function isBiasValid(b: WakeBias): boolean {
  return biasSum(b) === 100 && WAKE_CATS.every(c => b[c] >= 0 && b[c] <= 100);
}

/**
 * Adjust one wake-cat percentage, redistributing the delta across the other two
 * proportionally to their current ratio. Result always sums to exactly 100.
 */
export function adjustBias(current: WakeBias, edited: WakeCat, rawValue: number): WakeBias {
  const clamped = Math.max(0, Math.min(100, Math.round(rawValue)));
  const others = WAKE_CATS.filter(c => c !== edited) as [WakeCat, WakeCat];
  const remaining = 100 - clamped;
  const [a, b] = others;
  const sumOthers = current[a] + current[b];

  let newA: number;
  let newB: number;
  if (sumOthers === 0) {
    newA = Math.floor(remaining / 2);
    newB = remaining - newA;
  } else {
    newA = Math.round((current[a] / sumOthers) * remaining);
    newB = remaining - newA;
    if (newB < 0) {
      newB = 0;
      newA = remaining;
    }
  }

  const result = { ...current, [edited]: clamped } as WakeBias;
  result[a] = newA;
  result[b] = newB;
  return result;
}

/**
 * Split a total count across L/M/H according to the bias percentages.
 * Uses largest-remainder to guarantee the parts sum exactly to `total`.
 */
export function splitByBias(total: number, bias: WakeBias): Record<WakeCat, number> {
  if (total <= 0) return { L: 0, M: 0, H: 0 };
  const raw: Record<WakeCat, number> = {
    L: (total * bias.L) / 100,
    M: (total * bias.M) / 100,
    H: (total * bias.H) / 100,
  };
  const floors: Record<WakeCat, number> = {
    L: Math.floor(raw.L),
    M: Math.floor(raw.M),
    H: Math.floor(raw.H),
  };
  let used = floors.L + floors.M + floors.H;
  const remainders = WAKE_CATS.map(c => ({ cat: c, frac: raw[c] - floors[c] }))
    .sort((x, y) => y.frac - x.frac);
  let i = 0;
  while (used < total && i < remainders.length) {
    floors[remainders[i].cat]++;
    used++;
    i++;
  }
  return floors;
}
