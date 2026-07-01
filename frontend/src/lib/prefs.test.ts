import { beforeEach, describe, expect, it } from "vitest";

import { readPrefs, writePrefs } from "@/lib/prefs";

const KEY = "streamva.player";

describe("player prefs", () => {
  beforeEach(() => localStorage.clear());

  it("returns defaults when nothing is stored", () => {
    expect(readPrefs()).toEqual({ rate: 1, volume: 1, muted: false, autoplayNext: true });
  });

  it("merges stored values over defaults", () => {
    localStorage.setItem(KEY, JSON.stringify({ rate: 1.5 }));
    expect(readPrefs()).toMatchObject({ rate: 1.5, volume: 1, muted: false });
  });

  it("writePrefs round-trips and merges successive patches", () => {
    writePrefs({ rate: 2 });
    writePrefs({ muted: true });
    expect(readPrefs()).toMatchObject({ rate: 2, muted: true, autoplayNext: true });
  });

  it("falls back to defaults on corrupt JSON", () => {
    localStorage.setItem(KEY, "{not valid json");
    expect(readPrefs()).toEqual({ rate: 1, volume: 1, muted: false, autoplayNext: true });
  });
});
