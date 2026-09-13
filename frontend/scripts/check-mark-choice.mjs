import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import { createRequire } from "node:module";
import { pathToFileURL } from "node:url";
import ts from "typescript";

const source = await readFile(new URL("../client/src/lib/mark-choice.ts", import.meta.url), "utf8");
const compiled = ts.transpileModule(source, { compilerOptions: { module: ts.ModuleKind.ESNext, target: ts.ScriptTarget.ES2020 } });
const zodUrl = pathToFileURL(createRequire(import.meta.url).resolve("zod")).href;
const executable = compiled.outputText.replace('from "zod"', `from ${JSON.stringify(zodUrl)}`);
const {
  CHOICE_NAME_LIMIT, CHOICE_GOODS_LIMIT, ChoiceInputError, choiceText, choiceLength,
  validateChoiceInput, choiceIsStale, choiceServiceError, choiceHeading, markChoiceSchema, markChoiceReport,
} = await import(`data:text/javascript;base64,${Buffer.from(executable).toString("base64")}`);

const input = { first: "Яблоневый сад", second: "Я-ко", goods: "Розничный магазин фруктов" };
const rejectsField = (values, field) => assert.throws(
  () => validateChoiceInput(values),
  error => error instanceof ChoiceInputError && error.field === field,
);

// A business context and two alternatives are prerequisites, including whitespace-only input.
for (const field of ["first", "second", "goods"]) {
  rejectsField({ ...input, [field]: "" }, field);
  rejectsField({ ...input, [field]: " \n\t " }, field);
}
assert.deepEqual(validateChoiceInput({ first: " Яблоневый сад ", second: " Я-ко\n", goods: " Розничный магазин фруктов\t" }), input);

// Count Unicode characters rather than UTF-16 units, after canonical normalization.
assert.equal(choiceText("  и\u0306  "), "й");
assert.equal(choiceLength("  и\u0306  "), 1);
assert.equal(choiceLength("🍎"), 1);
for (const field of ["first", "second"]) {
  assert.equal(validateChoiceInput({ ...input, [field]: "🍎".repeat(CHOICE_NAME_LIMIT) })[field].length, CHOICE_NAME_LIMIT * 2);
  rejectsField({ ...input, [field]: "🍎".repeat(CHOICE_NAME_LIMIT + 1) }, field);
  assert.equal(validateChoiceInput({ ...input, [field]: "и\u0306".repeat(CHOICE_NAME_LIMIT) })[field], "й".repeat(CHOICE_NAME_LIMIT));
}
assert.equal(validateChoiceInput({ ...input, goods: "а".repeat(CHOICE_GOODS_LIMIT) }).goods.length, CHOICE_GOODS_LIMIT);
rejectsField({ ...input, goods: "а".repeat(CHOICE_GOODS_LIMIT + 1) }, "goods");

// Case, repeated spacing, and decomposed accents do not create a different alternative.
rejectsField({ ...input, second: "ЯБЛОНЕВЫЙ   САД" }, "second");
rejectsField({ ...input, second: "Яблоневый\t\nсад" }, "second");
rejectsField({ ...input, first: "Май", second: "Маи\u0306" }, "second");
assert.doesNotThrow(() => validateChoiceInput({ ...input, first: "АБ", second: "А Б" }));
assert.doesNotThrow(() => validateChoiceInput(input));

// Changing only the goods changes the legal context and invalidates the displayed analysis.
const saved = validateChoiceInput(input);
assert.equal(choiceIsStale({ ...saved, goods: " Розничный магазин фруктов " }, saved), false);
for (const field of ["first", "second", "goods"]) assert.equal(choiceIsStale({ ...saved, [field]: `${saved[field]} — изменено` }, saved), true);
assert.equal(choiceIsStale({ first: "Маи\u0306", second: "Я-ко", goods: saved.goods }, { ...saved, first: "Май" }), false);

const result = {
  mode: "demo",
  recommended: "second",
  summary: "Я-ко выглядит более самостоятельным названием для дальнейшей проверки.",
  first: {
    designation: saved.first, category: "suggestive", distinctiveness: "moderate", description_risk: "medium",
    goods_relation: "Вызывает ассоциации с выращиванием и продажей фруктов.",
    reasoning: "Связь с ассортиментом может ограничить различительную способность.",
    strengths: ["Покупателю понятна ассоциация с фруктами."], risks: ["Возможны похожие названия в этой сфере."],
  },
  second: {
    designation: saved.second, category: "fanciful", distinctiveness: "strong", description_risk: "low",
    goods_relation: "Не называет напрямую магазин или его ассортимент.",
    reasoning: "Необычное сочетание может восприниматься как самостоятельный бренд.",
    strengths: ["Есть потенциал различительной способности."], risks: ["Нужно проверить более ранние права."],
  },
  next_steps: ["Проверить более ранние товарные знаки для выбранных товаров и услуг."],
  limitations: ["Эта оценка не гарантирует регистрацию и зависит от указанного ассортимента."],
  registry_checked: false,
  sources: [{ title: "Гражданский кодекс, статья 1483", url: "https://www.consultant.ru/document/cons_doc_LAW_64629/" }],
};
assert.deepEqual(markChoiceSchema.parse(result), result);
const invalidResults = [
  { ...result, recommended: "first_by_default" },
  { ...result, mode: "production_mock" },
  { ...result, registry_checked: true },
  { ...result, registry_checked: undefined },
  { ...result, first: { ...result.first, category: "guaranteed_registration" } },
  { ...result, second: { ...result.second, reasoning: "" } },
  { ...result, summary: "" },
  { ...result, limitations: undefined },
  { ...result, sources: [{ title: "Source", url: "javascript:alert(1)" }] },
  { ...result, sources: [{ title: "Source", url: "http://example.com" }] },
];
for (const invalid of invalidResults) assert.equal(markChoiceSchema.safeParse(invalid).success, false);

// Only the expected service-unavailable contract exposes its actionable message to the user.
const fallback = "Не удалось выполнить сравнение. Попробуйте позже.";
const unavailable = { error: "comparison_unavailable", message: "Подключите модель анализа, чтобы сравнить свои обозначения." };
assert.equal(choiceServiceError(503, unavailable, fallback), unavailable.message);
for (const [status, detail] of [
  [500, unavailable], [401, unavailable], [422, unavailable],
  [503, { ...unavailable, error: "internal_error" }],
  [503, { error: "comparison_unavailable", message: { internal: "Private provider details" } }],
  [503, null], [503, "Private provider details"], [503, []],
]) assert.equal(choiceServiceError(status, detail, fallback), fallback);

// Recommendation follows the returned outcome; inconclusive/none never silently select the first name.
assert.equal(choiceHeading(result), `Для дальнейшей проверки — «${saved.second}»`);
assert.equal(choiceHeading({ ...result, recommended: "first" }), `Для дальнейшей проверки — «${saved.first}»`);
assert.equal(choiceHeading({ ...result, recommended: "none" }), "Стоит доработать оба варианта");
assert.equal(choiceHeading({ ...result, recommended: "inconclusive" }), "Пока нельзя выделить лучший вариант");

// Export uses the saved request that produced the result, even while the form has unsent edits.
const currentDraft = { first: "Новое название", second: "Другое название", goods: "Разработка программного обеспечения" };
assert.equal(choiceIsStale(currentDraft, saved), true);
const report = markChoiceReport(result, saved);
for (const expected of [
  saved.first, saved.second, `Товары и услуги: ${saved.goods}`, result.summary,
  result.first.goods_relation, result.second.goods_relation, result.first.reasoning, result.second.reasoning,
  ...result.first.strengths, ...result.first.risks, ...result.second.strengths, ...result.second.risks,
  ...result.next_steps, ...result.limitations, result.sources[0].url,
  "ДЕМОНСТРАЦИОННЫЙ ПРИМЕР", "не результат анализа подключённой модели", "ГРАНИЦЫ ОЦЕНКИ", "Поиск более ранних прав не выполнялся.",
]) assert.ok(report.includes(expected), `Missing report content: ${expected}`);
for (const unsent of Object.values(currentDraft)) assert.ok(!report.includes(unsent));
assert.ok(!markChoiceReport({ ...result, mode: "analysis" }, saved).includes("ДЕМОНСТРАЦИОННЫЙ ПРИМЕР"));
assert.ok(markChoiceReport({ ...result, recommended: "none" }, saved).includes("Стоит доработать оба варианта"));
assert.ok(markChoiceReport({ ...result, recommended: "inconclusive" }, saved).includes("Пока нельзя выделить лучший вариант"));

console.log("Mark-choice checks passed: required alternatives and goods, Unicode and limits, duplicate names, stale context, response validation, service errors, recommendation outcomes and honest saved-context reports.");
