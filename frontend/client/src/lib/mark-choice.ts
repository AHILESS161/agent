import { z } from "zod";

export const CHOICE_NAME_LIMIT = 120;
export const CHOICE_GOODS_LIMIT = 3000;
export type ChoiceInput = { first: string; second: string; goods: string };

export const categoryLabels = {
  fanciful: "Фантазийное", arbitrary: "Условное для этого бизнеса", suggestive: "Ассоциативное",
  descriptive: "Описательное", generic: "Общее название товара или услуги", unclear: "Нужно уточнить значение",
} as const;
export const distinctivenessLabels = { strong: "Сильная", moderate: "Умеренная", weak: "Слабая", unclear: "Не определена" } as const;
export const descriptionRiskLabels = { low: "Низкий", medium: "Умеренный", high: "Высокий", unclear: "Не определён" } as const;

const candidateSchema = z.object({
  designation: z.string().min(1),
  category: z.enum(["fanciful", "arbitrary", "suggestive", "descriptive", "generic", "unclear"]),
  distinctiveness: z.enum(["strong", "moderate", "weak", "unclear"]),
  description_risk: z.enum(["low", "medium", "high", "unclear"]),
  goods_relation: z.string().min(1), reasoning: z.string().min(1),
  strengths: z.array(z.string()), risks: z.array(z.string()),
});
export const markChoiceSchema = z.object({
  mode: z.enum(["analysis", "demo"]),
  recommended: z.enum(["first", "second", "none", "inconclusive"]),
  summary: z.string().min(1), first: candidateSchema, second: candidateSchema,
  next_steps: z.array(z.string()), limitations: z.array(z.string()), registry_checked: z.literal(false),
  sources: z.array(z.object({ title: z.string(), url: z.string().url().startsWith("https://") })),
});
export type MarkChoice = z.infer<typeof markChoiceSchema>;
export type ChoiceCandidate = MarkChoice["first"];

export class ChoiceInputError extends Error {
  constructor(public readonly field: keyof ChoiceInput, message: string) {
    super(message); this.name = "ChoiceInputError";
  }
}
export const choiceText = (value: string) => value.normalize("NFC").trim();
export const choiceLength = (value: string) => Array.from(choiceText(value)).length;

export function validateChoiceInput(input: ChoiceInput): ChoiceInput {
  const result = { first: choiceText(input.first), second: choiceText(input.second), goods: choiceText(input.goods) };
  for (const field of ["first", "second"] as const) {
    if (!result[field]) throw new ChoiceInputError(field, "Введите оба варианта названия.");
    if (choiceLength(result[field]) > CHOICE_NAME_LIMIT) throw new ChoiceInputError(field, `Название должно содержать не более ${CHOICE_NAME_LIMIT} символов.`);
  }
  if (!result.goods) throw new ChoiceInputError("goods", "Укажите товары или услуги: от них зависит оценка названия.");
  if (choiceLength(result.goods) > CHOICE_GOODS_LIMIT) throw new ChoiceInputError("goods", `Сократите описание до ${CHOICE_GOODS_LIMIT} символов.`);
  const comparable = (value: string) => value.toLocaleLowerCase("ru-RU").replace(/\s+/gu, " ");
  if (comparable(result.first) === comparable(result.second)) throw new ChoiceInputError("second", "Варианты совпадают. Укажите два разных названия.");
  return result;
}

export function choiceIsStale(input: ChoiceInput, saved: ChoiceInput): boolean {
  return (["first", "second", "goods"] as const).some(field => choiceText(input[field]) !== saved[field]);
}
export function choiceServiceError(status: number, detail: unknown, fallback: string): string {
  if (status === 503 && detail && typeof detail === "object" && "error" in detail &&
    detail.error === "comparison_unavailable" && "message" in detail && typeof detail.message === "string") return detail.message;
  return fallback;
}
export function choiceHeading(result: MarkChoice): string {
  if (result.recommended === "first" || result.recommended === "second") return `Для дальнейшей проверки — «${result[result.recommended].designation}»`;
  return result.recommended === "none" ? "Стоит доработать оба варианта" : "Пока нельзя выделить лучший вариант";
}
export function markChoiceReport(result: MarkChoice, input: ChoiceInput): string {
  const describe = (candidate: ChoiceCandidate, label: string) => [
    `${label}: ${candidate.designation}`, `Характер названия: ${categoryLabels[candidate.category]}`,
    `Различительная способность: ${distinctivenessLabels[candidate.distinctiveness]}`,
    `Риск описательности: ${descriptionRiskLabels[candidate.description_risk]}`,
    `Связь с бизнесом: ${candidate.goods_relation}`, candidate.reasoning,
    ...candidate.strengths.map(item => `Сильная сторона: ${item}`),
    ...candidate.risks.map(item => `На что обратить внимание: ${item}`),
  ].join("\n");
  return [
    "ВЫБОР ОБОЗНАЧЕНИЯ ДЛЯ РЕГИСТРАЦИИ ТОВАРНОГО ЗНАКА",
    ...(result.mode === "demo" ? ["ДЕМОНСТРАЦИОННЫЙ ПРИМЕР — не результат анализа подключённой модели."] : []),
    `Товары и услуги: ${input.goods}`, choiceHeading(result), result.summary,
    describe(result.first, "Первый вариант"), describe(result.second, "Второй вариант"),
    "СЛЕДУЮЩИЕ ШАГИ\n" + result.next_steps.map((item, index) => `${index + 1}. ${item}`).join("\n"),
    "ГРАНИЦЫ ОЦЕНКИ\nПоиск более ранних прав не выполнялся.\n" + result.limitations.join("\n"),
    "ИСТОЧНИКИ\n" + result.sources.map(source => `${source.title}: ${source.url}`).join("\n"),
  ].join("\n\n");
}
