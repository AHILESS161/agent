const BRAND_START_KEY = "registr:brand-start";
export const BRAND_START_TTL = 30 * 60 * 1000;

type BrandStartStorage = Pick<Storage, "getItem" | "setItem" | "removeItem">;
interface BrandStart {
  brand: string;
  business: string;
  createdAt: number;
  userId: number | null;
}

export function brandStartRoute(role = "client"): string {
  return `${role === "client" ? "/start" : "/intake"}?from=home`;
}

export function saveBrandStart(
  brand: string,
  business: string,
  userId: number | null,
  storage?: BrandStartStorage,
  now = Date.now(),
): void {
  const pending: BrandStart = { brand: brand.trim(), business: business.trim(), createdAt: now, userId };
  if (!pending.brand || !pending.business || pending.brand.length > 180 || pending.business.length > 500) {
    throw new RangeError("Проверьте название и описание деятельности.");
  }
  // Email confirmation can open another tab, so the short-lived handoff is shared across tabs.
  (storage ?? window.localStorage).setItem(BRAND_START_KEY, JSON.stringify(pending));
}

export function readBrandStart(userId: number | null, storage?: BrandStartStorage, now = Date.now()): BrandStart | null {
  try {
    const target = storage ?? window.localStorage;
    const raw = target.getItem(BRAND_START_KEY);
    if (!raw) return null;
    let pending: BrandStart;
    try { pending = JSON.parse(raw); } catch { target.removeItem(BRAND_START_KEY); return null; }
    if (!pending || typeof pending.brand !== "string" || !pending.brand.trim() || pending.brand.length > 180 ||
      typeof pending.business !== "string" || !pending.business.trim() || pending.business.length > 500 ||
      typeof pending.createdAt !== "number" || !Number.isFinite(pending.createdAt) ||
      pending.createdAt > now || now - pending.createdAt >= BRAND_START_TTL ||
      !(pending.userId === null || (Number.isInteger(pending.userId) && pending.userId > 0))) {
      target.removeItem(BRAND_START_KEY);
      return null;
    }
    // A signed-in user's start must not be applied when another account signs in on this browser.
    if (pending.userId !== null && pending.userId !== userId) return null;
    return pending;
  } catch { return null; }
}

export function consumeBrandStart(userId: number, storage?: BrandStartStorage, now = Date.now()): BrandStart | null {
  try {
    const target = storage ?? window.localStorage;
    const pending = readBrandStart(userId, target, now);
    if (pending) target.removeItem(BRAND_START_KEY);
    return pending;
  } catch { return null; }
}
