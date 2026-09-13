import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";

const read = (path) => readFile(new URL(path, import.meta.url), "utf8");
const [app, publicLayout, authLayout, aboutPage, clientLayout] = await Promise.all([
  read("../client/src/App.tsx"),
  read("../client/src/components/public-layout.tsx"),
  read("../client/src/components/auth-layout.tsx"),
  read("../client/src/pages/home.tsx"),
  read("../client/src/components/client-portal-layout.tsx"),
]);

const aboutRoute = app.indexOf('location === "/about"');
const authGuard = app.indexOf("if (!isAuthenticated)");
assert.ok(aboutRoute >= 0 && aboutRoute < authGuard, "About must be available without authentication");
assert.ok(!app.includes('location === "/"') || app.indexOf('location === "/"') > authGuard, "Root must not bypass authentication");
assert.match(app, /location === "\/principles".*Redirect to="\/about\?section=principles"/s);

const publicNav = publicLayout.match(/<nav aria-label="Основная навигация">([\s\S]*?)<\/nav>/)?.[1] || "";
const publicLabels = [...publicNav.matchAll(/<HomeSectionLink[^>]*>([^<]+)<\/HomeSectionLink>/g)].map((match) => match[1]);
assert.deepEqual(publicLabels, ["Как это работает", "Результат", "Вопросы"]);
assert.ok(!publicNav.includes("Принципы сервиса"));
assert.ok(publicLayout.includes("/about?section=${section}"));

assert.ok(authLayout.includes('href="/about?section=top"'));
assert.ok(authLayout.includes("three-gods.png"));

const principles = aboutPage.indexOf('id="principles"');
const approach = aboutPage.indexOf('id="approach"');
assert.ok(principles >= 0 && principles < approach, "Principles summary must precede How it works");
for (const image of ["themis.png", "plutus.png", "tyche.png"]) assert.ok(aboutPage.includes(image));
assert.ok(!aboutPage.includes("three-gods.png"));

const applications = clientLayout.indexOf('label: "Мои заявки"');
const reply = clientLayout.indexOf('label: "Ответ Роспатенту"');
const compare = clientLayout.indexOf('label: "Сравнение обозначений"');
assert.ok(applications >= 0 && applications < reply && reply < compare, "Client sections are out of order");

console.log("Public journey checks passed: auth entry, public About tabs, compact principles portraits and client navigation order.");
