export interface ComparedPart {
  text: string;
  same: boolean;
}

export interface MarkComparison {
  left: string;
  right: string;
  leftParts: ComparedPart[];
  rightParts: ComparedPart[];
  exact: boolean;
  normalized: boolean;
  lengths: [number, number];
  commonWords: string[];
  mixedScript: boolean;
}

export const MARK_CHARACTER_LIMIT = 120;

export function markLength(value: string): number {
  return Array.from(value.normalize("NFC").trim()).length;
}

export function compareMarks(first: string, second: string): MarkComparison {
  const left = first.normalize("NFC").trim();
  const right = second.normalize("NFC").trim();
  const a = Array.from(left);
  const b = Array.from(right);
  if (!a.length || !b.length) throw new RangeError("Введите оба обозначения для сравнения.");
  if (a.length > MARK_CHARACTER_LIMIT || b.length > MARK_CHARACTER_LIMIT) {
    throw new RangeError(`Обозначение должно содержать не более ${MARK_CHARACTER_LIMIT} символов.`);
  }

  // The common subsequence aligns repeated characters without treating a literal difference as legal similarity.
  const table = Array.from({ length: a.length + 1 }, () => new Uint16Array(b.length + 1));
  for (let i = a.length - 1; i >= 0; i--) {
    for (let j = b.length - 1; j >= 0; j--) {
      table[i][j] = a[i] === b[j] ? 1 + table[i + 1][j + 1] : Math.max(table[i + 1][j], table[i][j + 1]);
    }
  }
  const leftMatched = new Set<number>();
  const rightMatched = new Set<number>();
  let i = 0;
  let j = 0;
  while (i < a.length && j < b.length) {
    if (a[i] === b[j]) {
      leftMatched.add(i++);
      rightMatched.add(j++);
    } else if (table[i + 1][j] >= table[i][j + 1]) {
      i++;
    } else {
      j++;
    }
  }
  const normalize = (value: string) => value.toLocaleLowerCase("ru-RU").replace(/\s/gu, "");
  const words = (value: string) => value.toLocaleLowerCase("ru-RU").match(/[\p{L}\p{N}]+/gu) || [];
  const rightWords = new Set(words(right));
  return {
    left,
    right,
    leftParts: a.map((text, index) => ({ text, same: leftMatched.has(index) })),
    rightParts: b.map((text, index) => ({ text, same: rightMatched.has(index) })),
    exact: left === right,
    normalized: normalize(left) === normalize(right),
    lengths: [a.length, b.length],
    commonWords: [...new Set(words(left))].filter(word => rightWords.has(word)),
    mixedScript: /\p{Script=Cyrillic}/u.test(left + right) && /\p{Script=Latin}/u.test(left + right),
  };
}

export function comparisonReport(result: MarkComparison, goods: string): string {
  return [
    "ТЕКСТОВОЕ СРАВНЕНИЕ ОБОЗНАЧЕНИЙ",
    `А: ${result.left}\nБ: ${result.right}`,
    `Точное совпадение без внешних пробелов: ${result.exact ? "Совпадают" : "Различаются"}\n` +
      `Без учёта регистра и пробелов: ${result.normalized ? "Совпадают" : "Различаются"}\n` +
      `Длина обозначений: А — ${result.lengths[0]}, Б — ${result.lengths[1]}\n` +
      `Совпадающие слова: ${result.commonWords.join(", ") || "Нет"}`,
    `Товары и услуги (описание пользователя, не оценивались):\n${goods.trim() || "Не указаны"}`,
    "Это техническое сравнение текста. Сходство до степени смешения, однородность товаров, вероятность регистрации " +
      "и нарушение прав не оцениваются. Фонетический, смысловой и графический анализ не выполнялись.",
    ...(result.mixedScript ? ["Кириллица и латиница считаются разными символами."] : []),
  ].join("\n\n");
}
