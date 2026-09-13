import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import ts from "typescript";

const source = await readFile(new URL("../client/src/lib/service-navigation.ts", import.meta.url), "utf8");
const compiled = ts.transpileModule(source, {
  compilerOptions: { module: ts.ModuleKind.ESNext, target: ts.ScriptTarget.ES2020 },
});
const { readServiceRoute, serviceHref } = await import(`data:text/javascript;base64,${Buffer.from(compiled.outputText).toString("base64")}`);

// Shared links may include a query inside the hash; in-app navigation puts it
// before the hash. Both must open the same tool and application.
const expected = { path: "/services", tool: "compare", applicationId: 42 };
assert.deepEqual(readServiceRoute("/services?tool=compare&application=42", ""), expected);
assert.deepEqual(readServiceRoute("/services", "?tool=compare&application=42"), expected);

// An explicit hash query wins over stale outer parameters, including when it
// deliberately omits application context.
assert.deepEqual(readServiceRoute("/services?tool=compare&application=42", "?tool=reply&application=9"), expected);
assert.equal(readServiceRoute("/services?tool=reply", "?application=42").applicationId, undefined);
assert.equal(readServiceRoute("/services?", "?tool=compare&application=42").applicationId, undefined);
assert.equal(readServiceRoute("/services?", "?tool=compare&application=42").tool, "reply");
assert.equal(readServiceRoute("/services", "?tool=unknown").tool, "reply");

// wouter may retain the old search when leaving tools. Opening a tool from an
// unrelated page must not silently attach that old application.
for (const path of ["/", "/dashboard", "/start", "/profile", "/how-it-works", "/applications/new"]) {
  const route = readServiceRoute(path, "?application=42&tool=compare");
  assert.equal(route.applicationId, undefined, `Stale application leaked from ${path}`);
  assert.equal(serviceHref("reply", route.applicationId), "/services?tool=reply");
}

// Entering tools from an application uses the application's actual path id,
// never a conflicting id still present in the browser search.
const application = readServiceRoute("/applications/7?step=response", "?application=42");
assert.equal(application.applicationId, 7);
assert.equal(serviceHref("reply", application.applicationId), "/services?tool=reply&application=7");
assert.equal(readServiceRoute("/applications/7/", "").applicationId, 7);
assert.equal(readServiceRoute("/applications/7/documents", "?application=42").applicationId, undefined);

// Switching in either direction and revisiting previous URLs keeps both the
// selected tool and application, without depending on mutable component state.
const replyHref = serviceHref("reply", 42);
const reply = readServiceRoute(replyHref, "");
const compareHref = serviceHref("compare", reply.applicationId);
const compare = readServiceRoute(compareHref, "");
assert.equal(compareHref, "/services?tool=compare&application=42");
assert.deepEqual(compare, expected);
assert.equal(serviceHref("reply", compare.applicationId), replyHref);
assert.deepEqual(readServiceRoute(replyHref, ""), { path: "/services", tool: "reply", applicationId: 42 });
assert.deepEqual(readServiceRoute(compareHref, ""), expected);

// Malformed or non-representable ids must not become API or navigation targets.
for (const invalid of ["", "0", "-3", "1.5", "wat", "9007199254740992"]) {
  assert.equal(readServiceRoute("/services", `?application=${invalid}`).applicationId, undefined);
}
for (const invalid of [0, -2, 1.5, Number.NaN, Number.POSITIVE_INFINITY, Number.MAX_SAFE_INTEGER + 1]) {
  assert.equal(serviceHref("compare", invalid), "/services?tool=compare");
}
assert.equal(serviceHref("reply"), "/services?tool=reply");

console.log("Client navigation checks passed: hash/search links, explicit query priority, stale application isolation, application context, tool-switch history and safe IDs.");
