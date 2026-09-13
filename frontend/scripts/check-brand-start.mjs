import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import ts from "typescript";

const source = await readFile(new URL("../client/src/lib/brand-start.ts", import.meta.url), "utf8");
const compiled = ts.transpileModule(source, { compilerOptions: { module: ts.ModuleKind.ESNext, target: ts.ScriptTarget.ES2020 } });
const { saveBrandStart, readBrandStart, consumeBrandStart, brandStartRoute, BRAND_START_TTL } = await import(`data:text/javascript;base64,${Buffer.from(compiled.outputText).toString("base64")}`);
const now = 1_000_000;
const values = new Map();
const tab = () => ({
  getItem: key => values.get(key) ?? null,
  setItem: (key, value) => values.set(key, value),
  removeItem: key => values.delete(key),
});
const firstTab = tab();
const emailTab = tab();

// The email confirmation tab sees the guest's start; checking the post-login route does not consume it.
saveBrandStart(" Квелтаро ", " Кафе и выпечка ", null, firstTab, now);
const pending = readBrandStart(7, emailTab, now + 60_000);
assert.equal(pending.brand, "Квелтаро");
assert.equal(pending.business, "Кафе и выпечка");
assert.equal(brandStartRoute("client"), "/start?from=home");
assert.deepEqual(readBrandStart(7, firstTab, now + 60_000), pending);

// Intake consumes once, without replacing the user's existing applicant draft.
firstTab.setItem("registr:intake-draft:7", JSON.stringify({ name: "Заявитель", inn: "1234567890" }));
assert.deepEqual(consumeBrandStart(7, emailTab, now + 60_000), pending);
assert.equal(consumeBrandStart(7, firstTab, now + 60_001), null);
assert.equal(JSON.parse(firstTab.getItem("registr:intake-draft:7")).name, "Заявитель");
for (const role of ["admin", "lawyer", "manager"]) assert.equal(brandStartRoute(role), "/intake?from=home");

// Starts made while authenticated belong to that account, not the next person using the browser.
saveBrandStart("Бренд", "Услуги", 7, firstTab, now);
assert.equal(readBrandStart(8, emailTab, now + 1), null);
assert.equal(consumeBrandStart(8, emailTab, now + 1), null);
assert.equal(readBrandStart(null, emailTab, now + 1), null);
assert.equal(consumeBrandStart(7, firstTab, now + 1).brand, "Бренд");

saveBrandStart("Бренд", "Услуги", null, firstTab, now);
assert.ok(readBrandStart(7, emailTab, now + BRAND_START_TTL - 1));
assert.equal(readBrandStart(7, emailTab, now + BRAND_START_TTL), null);
saveBrandStart("Бренд", "Услуги", null, firstTab, now + 100);
assert.equal(readBrandStart(7, emailTab, now), null);
firstTab.setItem("registr:brand-start", "broken json");
assert.equal(readBrandStart(7, emailTab, now), null);
firstTab.setItem("registr:brand-start", JSON.stringify({ brand: "Бренд", business: "Услуги", createdAt: now }));
assert.equal(readBrandStart(7, emailTab, now), null);
assert.throws(() => saveBrandStart(" ", "Услуги", null, firstTab, now), RangeError);
const denied = { getItem() { throw new Error("Blocked"); }, setItem() { throw new Error("Blocked"); }, removeItem() { throw new Error("Blocked"); } };
assert.equal(readBrandStart(7, denied, now), null);
assert.equal(consumeBrandStart(7, denied, now), null);
assert.throws(() => saveBrandStart("Бренд", "Услуги", null, denied, now), /Blocked/);
console.log("Brand-start checks passed: cross-tab confirmation, role routes, one-time intake handoff, applicant draft isolation, account ownership, expiry and unavailable storage.");
