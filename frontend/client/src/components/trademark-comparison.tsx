import { useId, useRef, useState, type FormEvent } from "react";
import { ArrowRight, Copy, Download, ScanText } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import {
  compareMarks,
  comparisonReport,
  markLength,
  MARK_CHARACTER_LIMIT,
  type ComparedPart,
  type MarkComparison,
} from "@/lib/compare-marks";

interface ComparisonSnapshot {
  first: string;
  second: string;
  goods: string;
  result: MarkComparison;
}

function MarkParts({ parts }: { parts: ComparedPart[] }) {
  return (
    <span className="whitespace-pre-wrap break-words">
      {parts.map((part, index) => (
        <span key={index} className={part.same ? "" : "rounded-sm bg-[#e8d8b6] text-[#483b29] underline decoration-[#9b8258] underline-offset-4"}>
          {part.text}
        </span>
      ))}
    </span>
  );
}

export function TrademarkComparison() {
  const id = useId();
  const firstRef = useRef<HTMLInputElement>(null);
  const secondRef = useRef<HTMLInputElement>(null);
  const [first, setFirst] = useState("");
  const [second, setSecond] = useState("");
  const [goods, setGoods] = useState("");
  const [snapshot, setSnapshot] = useState<ComparisonSnapshot | null>(null);
  const [error, setError] = useState("");
  const [status, setStatus] = useState("");
  const result = snapshot?.result;
  const savedGoods = snapshot?.goods.trim() ?? "";
  const stale = !!snapshot && (snapshot.first !== first || snapshot.second !== second || snapshot.goods !== goods);
  const firstLength = markLength(first);
  const secondLength = markLength(second);
  const invalidFirst = firstLength > MARK_CHARACTER_LIMIT || (!!error && !firstLength);
  const invalidSecond = secondLength > MARK_CHARACTER_LIMIT || (!!error && !secondLength);

  function updateField(setter: (value: string) => void, value: string) {
    setter(value);
    setError("");
    setStatus("");
  }

  function compare(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setStatus("");
    try {
      const next = compareMarks(first, second);
      setSnapshot({ first, second, goods, result: next });
      setError("");
      setStatus("Сравнение готово. Внешние пробелы не учитываются.");
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "Не удалось сравнить обозначения.");
      (!firstLength || firstLength > MARK_CHARACTER_LIMIT ? firstRef : secondRef).current?.focus();
    }
  }

  async function copy() {
    if (!snapshot || stale) return;
    try {
      if (!navigator.clipboard?.writeText) throw new Error("Clipboard unavailable");
      await navigator.clipboard.writeText(comparisonReport(snapshot.result, snapshot.goods));
      setStatus("Результат скопирован.");
    } catch {
      setStatus("Не удалось скопировать. Скачайте результат в TXT.");
    }
  }

  function download() {
    if (!snapshot || stale) return;
    const blob = new Blob(["\ufeff", comparisonReport(snapshot.result, snapshot.goods)], { type: "text/plain;charset=utf-8" });
    const url = URL.createObjectURL(blob);
    const link = document.createElement("a");
    link.href = url;
    link.download = "registr-sravnenie-znakov.txt";
    document.body.append(link);
    link.click();
    link.remove();
    window.setTimeout(() => URL.revokeObjectURL(url), 1500);
    setStatus("Файл TXT подготовлен.");
  }

  return (
    <div className="space-y-6 text-[#38322e]">
      <div className="max-w-2xl space-y-2">
        <h2 className="font-serif text-3xl sm:text-4xl">Сравнение товарных знаков</h2>
        <p className="text-sm leading-relaxed text-[#746e66]">Введите два названия, чтобы увидеть совпадения и различия в тексте. Это первый шаг к сравнению обозначений.</p>
      </div>
      <div className="grid items-start gap-6 lg:grid-cols-2">
        <form onSubmit={compare} noValidate className="space-y-6 rounded-3xl border border-[#ded9cf] bg-[#fcfbf8] p-5 sm:p-7" aria-label="Сравнение обозначений">
          <div className="space-y-2">
            <Label htmlFor={`${id}-first`} className="text-[#38322e]">Первое обозначение</Label>
            <Input id={`${id}-first`} ref={firstRef} value={first} required autoComplete="off" placeholder="Например, ЛУННЫЙ САД" onChange={event => updateField(setFirst, event.target.value)} aria-invalid={invalidFirst} aria-describedby={`${id}-first-hint${error ? ` ${id}-error` : ""}`} className="h-12 rounded-xl border-[#ded9cf] bg-white text-[#38322e] placeholder:text-[#8c867e] focus-visible:ring-[#9b8258]" />
            <p id={`${id}-first-hint`} className={`text-xs ${invalidFirst ? "text-red-700" : "text-[#746e66]"}`}>{firstLength} / {MARK_CHARACTER_LIMIT} символов</p>
          </div>
          <div className="space-y-2">
            <Label htmlFor={`${id}-second`} className="text-[#38322e]">Второе обозначение</Label>
            <Input id={`${id}-second`} ref={secondRef} value={second} required autoComplete="off" placeholder="Например, ЛУННЫЙ ЦВЕТ" onChange={event => updateField(setSecond, event.target.value)} aria-invalid={invalidSecond} aria-describedby={`${id}-second-hint${error ? ` ${id}-error` : ""}`} className="h-12 rounded-xl border-[#ded9cf] bg-white text-[#38322e] placeholder:text-[#8c867e] focus-visible:ring-[#9b8258]" />
            <p id={`${id}-second-hint`} className={`text-xs ${invalidSecond ? "text-red-700" : "text-[#746e66]"}`}>{secondLength} / {MARK_CHARACTER_LIMIT} символов</p>
          </div>
          <details className="rounded-xl border border-[#ded9cf] bg-white px-4 py-3">
            <summary className="cursor-pointer text-sm text-[#584b41] focus-visible:outline-[#9b8258]">Добавить товары и услуги <span className="text-xs text-[#746e66]">· необязательно</span></summary>
            <div className="mt-4 space-y-2">
              <Label htmlFor={`${id}-goods`} className="text-[#38322e]">Описание для заметки</Label>
              <Textarea id={`${id}-goods`} value={goods} maxLength={3000} onChange={event => updateField(setGoods, event.target.value)} placeholder="Например, цветы и доставка букетов" aria-describedby={`${id}-goods-hint`} className="min-h-24 rounded-xl border-[#ded9cf] bg-[#fcfbf8] text-[#38322e] placeholder:text-[#8c867e] focus-visible:ring-[#9b8258]" />
              <p id={`${id}-goods-hint`} className="text-xs leading-relaxed text-[#746e66]">Сохраним в результате как вашу заметку. Однородность товаров и услуг здесь не оценивается.</p>
            </div>
          </details>
          {error && <p id={`${id}-error`} role="alert" className="text-sm text-red-700">{error}</p>}
          <Button type="submit" className="w-full rounded-full border-[#584b41] bg-[#584b41] text-white hover:bg-[#483d34] sm:w-auto">{stale ? "Обновить сравнение" : "Сравнить обозначения"}<ArrowRight aria-hidden="true" /></Button>
        </form>

        <section aria-labelledby={`${id}-result-title`} className="min-w-0 rounded-3xl border border-[#ded9cf] bg-white p-5 sm:p-7">
          <h3 id={`${id}-result-title`} className="font-serif text-2xl">Результат сравнения</h3>
          {!result ? (
            <div className="py-10 text-sm leading-relaxed text-[#746e66]">
              <ScanText className="mb-5 h-9 w-9 text-[#9b8258]" aria-hidden="true" />
              <p>Здесь появятся обозначения с выделенными различиями, совпадающие слова и текстовый отчёт.</p>
              <p className="mt-3">Для начала нужны только два названия.</p>
            </div>
          ) : (
            <div className="mt-5 space-y-5">
              {stale && <p role="status" className="rounded-xl bg-[#f4eddf] p-3 text-sm text-[#665233]">Данные изменились. Обновите сравнение перед копированием или скачиванием.</p>}
              <div className="grid gap-3 sm:grid-cols-2">
                {[{ name: "Первое обозначение", parts: result.leftParts }, { name: "Второе обозначение", parts: result.rightParts }].map(mark => (
                  <div key={mark.name} className="min-w-0 rounded-xl bg-[#f4f1eb] p-4">
                    <p className="mb-3 text-xs text-[#746e66]">{mark.name}</p>
                    <p className="font-serif text-2xl leading-relaxed"><MarkParts parts={mark.parts} /></p>
                  </div>
                ))}
              </div>
              <p className="text-xs text-[#746e66]">Цветом и подчёркиванием выделены отличающиеся символы с учётом регистра.</p>
              <dl className="divide-y divide-[#e8e3da] text-sm">
                {[
                  ["Точное совпадение", result.exact ? "Совпадают" : "Различаются"],
                  ["Без учёта регистра и пробелов", result.normalized ? "Совпадают" : "Различаются"],
                  ["Количество символов", `Первое: ${result.lengths[0]} · Второе: ${result.lengths[1]}`],
                  ["Совпадающие слова", result.commonWords.join(", ") || "Нет"],
                ].map(([label, value]) => (
                  <div key={label} className="grid gap-1 py-3 sm:grid-cols-2 sm:gap-4">
                    <dt className="text-[#746e66]">{label}</dt><dd className="min-w-0 break-words font-medium sm:text-right">{value}</dd>
                  </div>
                ))}
              </dl>
              {result.mixedScript && <p className="rounded-xl bg-[#f4f1eb] p-3 text-xs leading-relaxed text-[#746e66]">В обозначениях есть кириллица и латиница. Внешне похожие буквы разных алфавитов считаются разными символами.</p>}
              {savedGoods && <div className="text-sm"><p className="mb-1 text-[#746e66]">Товары и услуги · ваша заметка, без оценки</p><p className="whitespace-pre-wrap break-words">{savedGoods}</p></div>}
              <div className="flex flex-wrap gap-2">
                <Button type="button" variant="outline" onClick={copy} disabled={stale} className="rounded-full border-[#ded9cf] text-[#584b41]"><Copy aria-hidden="true" />Копировать</Button>
                <Button type="button" variant="outline" onClick={download} disabled={stale} className="rounded-full border-[#ded9cf] text-[#584b41]"><Download aria-hidden="true" />Скачать TXT</Button>
              </div>
            </div>
          )}
          <p role="status" className="mt-4 min-h-5 text-xs leading-relaxed text-[#746e66]">{status}</p>
        </section>
      </div>
      <p className="max-w-4xl text-xs leading-relaxed text-[#746e66]">Инструмент сопоставляет только текст. Фонетический, смысловой и графический анализ, сходство до степени смешения, однородность товаров и вероятность регистрации здесь не оцениваются.</p>
    </div>
  );
}
