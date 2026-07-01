// Persisted player preferences (speed, volume, autoplay) in localStorage.

export interface PlayerPrefs {
  rate: number;
  volume: number;
  muted: boolean;
  autoplayNext: boolean;
}

const KEY = "streamva.player";
const DEFAULTS: PlayerPrefs = { rate: 1, volume: 1, muted: false, autoplayNext: true };

export function readPrefs(): PlayerPrefs {
  try {
    return { ...DEFAULTS, ...JSON.parse(localStorage.getItem(KEY) || "{}") };
  } catch {
    return { ...DEFAULTS };
  }
}

export function writePrefs(patch: Partial<PlayerPrefs>): void {
  try {
    localStorage.setItem(KEY, JSON.stringify({ ...readPrefs(), ...patch }));
  } catch {
    /* ignore */
  }
}
