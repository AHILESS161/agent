import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import ts from "typescript";

// Compile the production utility in memory so this check also runs on Node 20.
const source = await readFile(new URL("../client/src/lib/compare-marks.ts", import.meta.url), "utf8");
const compiled = ts.transpileModule(source, { compilerOptions: { module: ts.ModuleKind.ESNext, target: ts.ScriptTarget.ES2020 } });
const { compareMarks, comparisonReport, markLength } = await import(`data:text/javascript;base64,${Buffer.from(compiled.outputText).toString("base64")}`);

const same = compareMarks("  КВЕЛТАРО ", "КВЕЛТАРО");
assert.equal(same.exact, true);
assert.ok(same.leftParts.every(part => part.same));
const caseAndSpace = compareMarks("КВЕЛ ТАРО", "квелтаро");
assert.equal(caseAndSpace.exact, false);
assert.equal(caseAndSpace.normalized, true);
const homograph = compareMarks("СОК", "COK");
assert.equal(homograph.normalized, false);
assert.equal(homograph.mixedScript, true);
const repeated = compareMarks("ААБА", "АБА");
assert.equal(repeated.leftParts.filter(part => part.same).map(part => part.text).join(""), "АБА");
assert.equal(repeated.rightParts.filter(part => part.same).length, 3);
assert.equal(compareMarks("е\u0308", "ё").exact, true);
assert.equal(markLength("  е\u0308🌟  "), 2);
assert.deepEqual(compareMarks("Дом дом", "ДОМ и сад").commonWords, ["дом"]);
const emoji = compareMarks("А🌟", "А");
assert.deepEqual(emoji.lengths, [2, 1]);
assert.equal(emoji.leftParts[1].same, false);
assert.throws(() => compareMarks("а".repeat(121), "б"), RangeError);
assert.throws(() => compareMarks("а", "🌟".repeat(121)), RangeError);
assert.equal(compareMarks("🌟".repeat(120), "🌟").lengths[0], 120);
assert.throws(() => compareMarks(" \n ", "б"), /Введите оба/);
assert.throws(() => compareMarks("а", ""), /Введите оба/);
const report = comparisonReport(homograph, "Цветы и доставка");
assert.ok(report.includes("Цветы и доставка"));
assert.ok(report.includes("не оценивались"));
assert.ok(report.includes("Кириллица и латиница считаются разными символами."));
assert.ok(report.includes("смысловой и графический анализ не выполнялись"));
console.log("Comparison checks passed: exact matches, whitespace, case, homographs, repeated characters, Unicode, limits and report context.");
