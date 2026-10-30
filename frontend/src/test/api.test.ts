import { beforeEach, describe, it, expect, vi } from "vitest";
import { api, query, request, setSession } from "../lib/api";
const json = (value: unknown, status = 200) =>
  new Response(JSON.stringify(value), {
    status,
    headers: { "Content-Type": "application/json" },
  });
beforeEach(() => {
  setSession(null);
  vi.unstubAllGlobals();
});
describe("API boundary", () => {
  it("encodes filters without conflating missing with zero", () => {
    const p = new URLSearchParams(
      query({ offset: 0, q: "tea & rice", category: undefined }).slice(1),
    );
    expect(p.get("offset")).toBe("0");
    expect(p.get("q")).toBe("tea & rice");
    expect(p.has("category")).toBe(false);
  });
  it("sends JSON authentication and preserves decimal strings", async () => {
    const fetcher = vi
      .fn()
      .mockResolvedValue(json({ access_token: "test", token_type: "bearer" }));
    vi.stubGlobal("fetch", fetcher);
    await api.login("user@example.com", "pass");
    expect(fetcher.mock.calls[0][0]).toBe("/api/login");
    expect(JSON.parse(fetcher.mock.calls[0][1].body)).toEqual({
      email: "user@example.com",
      password: "pass",
    });
  });
  it("refreshes concurrent expired requests once using form encoding", async () => {
    setSession({
      access_token: "expired",
      token_type: "bearer",
      refresh_token: "refresh",
    });
    let refreshed = false;
    const fetcher = vi.fn(async (url: string, init: RequestInit) => {
      if (url.endsWith("/refresh")) {
        await Promise.resolve();
        refreshed = true;
        expect(init.body).toBeInstanceOf(URLSearchParams);
        return json({ access_token: "new", token_type: "bearer" });
      }
      if (!refreshed) return json({ detail: "Expired" }, 401);
      expect(new Headers(init.headers).get("Authorization")).toBe("Bearer new");
      return json({ id: 1 });
    });
    vi.stubGlobal("fetch", fetcher);
    await Promise.all([api.me(), api.me()]);
    expect(
      fetcher.mock.calls.filter(([url]) => url.endsWith("/refresh")),
    ).toHaveLength(1);
  });
  it("ends a session when refresh is unavailable", async () => {
    setSession({ access_token: "expired", token_type: "bearer" });
    const expired = vi.fn();
    window.addEventListener("session-expired", expired, { once: true });
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue(json({ detail: "Expired" }, 401)),
    );
    await expect(api.me()).rejects.toThrow("Expired");
    expect(expired).toHaveBeenCalledOnce();
  });
  it("explains field validation failures", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue(
        json(
          {
            detail: [
              { loc: ["body", "amount"], msg: "Amount must be positive" },
            ],
          },
          422,
        ),
      ),
    );
    await expect(api.cashflow("-1", 3)).rejects.toThrow(
      "Amount must be positive",
    );
  });
  it("does not replace network failure with fake data", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockRejectedValue(new TypeError("Failed to fetch")),
    );
    await expect(api.me()).rejects.toThrow("Could not reach PorerHishab");
  });
  it("uses confirmed category correction and purchase contracts", async () => {
    const fetcher = vi.fn().mockImplementation(async () => json({}));
    vi.stubGlobal("fetch", fetcher);
    await api.correctCategory(17, "Groceries");
    expect(fetcher.mock.calls[0][0]).toBe("/api/transactions/17/category");
    expect(fetcher.mock.calls[0][1].method).toBe("PATCH");
    const body = {
      starting_balance: "100.00",
      purchase_amount: "10.00",
      safety_buffer: "20.00",
      horizon_days: 30,
    };
    await api.decision(body);
    expect(fetcher.mock.calls[1][0]).toBe(
      "/api/finance/coach/spending-decision",
    );
    expect(JSON.parse(fetcher.mock.calls[1][1].body)).toEqual(body);
  });
  it("does not set JSON content type on CSV uploads", async () => {
    const fetcher = vi.fn().mockImplementation(async () => json({}));
    vi.stubGlobal("fetch", fetcher);
    await api.upload(new File(["amount\n-1.00"], "records.csv"));
    expect(fetcher.mock.calls[0][1].body).toBeInstanceOf(FormData);
    expect(
      new Headers(fetcher.mock.calls[0][1].headers).has("Content-Type"),
    ).toBe(false);
  });
  it("handles bodyless success responses", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue(new Response(null, { status: 204 })),
    );
    expect(await request("/example", { method: "DELETE" })).toBeUndefined();
  });
  it("does not resurrect a signed-out session when a refresh finishes late", async () => {
    setSession({
      access_token: "old",
      token_type: "bearer",
      refresh_token: "refresh",
    });
    let finish: (value: Response) => void = () => {};
    const pending = new Promise<Response>((resolve) => {
      finish = resolve;
    });
    const fetcher = vi
      .fn()
      .mockResolvedValueOnce(json({ detail: "Expired" }, 401))
      .mockImplementationOnce(() => pending)
      .mockResolvedValue(json({ id: 1 }));
    vi.stubGlobal("fetch", fetcher);
    const request = api.me();
    await vi.waitFor(() => expect(fetcher).toHaveBeenCalledTimes(2));
    setSession(null);
    finish(json({ access_token: "late", token_type: "bearer" }));
    await expect(request).rejects.toThrow("Expired");
    await api.me();
    expect(
      new Headers(fetcher.mock.calls[2][1].headers).has("Authorization"),
    ).toBe(false);
  });
});
