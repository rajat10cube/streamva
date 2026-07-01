import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { getCourses, setUnauthorizedHandler } from "@/api";

function jsonResponse(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "Content-Type": "application/json" },
  });
}

describe("api client getJSON", () => {
  beforeEach(() => setUnauthorizedHandler(null));
  afterEach(() => vi.unstubAllGlobals());

  it("invokes the unauthorized handler and throws on 401", async () => {
    const onUnauth = vi.fn();
    setUnauthorizedHandler(onUnauth);
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(new Response("", { status: 401 })));

    await expect(getCourses()).rejects.toThrow("unauthorized");
    expect(onUnauth).toHaveBeenCalledOnce();
  });

  it("throws on non-OK responses other than 401", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(new Response("", { status: 500 })));
    await expect(getCourses()).rejects.toThrow("500");
  });

  it("returns parsed JSON on success", async () => {
    const payload = { courses: [], categories: ["Udemy"] };
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(jsonResponse(payload)));
    await expect(getCourses()).resolves.toEqual(payload);
  });
});
