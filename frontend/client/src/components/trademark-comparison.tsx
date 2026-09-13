import { useId, useRef, useState, type FormEvent } from "react";
import { ArrowRight, Copy, Download, Loader2, Scale } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import { api, ApiError } from "@/lib/api";
import {
  CHOICE_NAME_LIMIT, CHOICE_GOODS_LIMIT, ChoiceInputError,
  categoryLabels, choiceHeading, choiceIsStale, choiceLength, choiceServiceError,
  descriptionRiskLabels, distinctivenessLabels, markChoiceReport, markChoiceSchema,
  validateChoiceInput, type ChoiceCandidate, type ChoiceInput, type MarkChoice,
} from "@/lib/mark-choice";

interface ChoiceSnapshot { input: ChoiceInput; result: MarkChoice }

function CandidateCard({ candidate, preferred }: { candidate: ChoiceCandidate; preferred: boolean }) {
  return <article className={`min-w-0 rounded-2xl border p-5 sm:p-6 ${preferred ? "border-[#9b8258] bg-[#f4f1eb]" : "border-[#ded9cf] bg-white"}`}>
    <p className="text-xs font-medium text-[#746e66]">{categoryLabels[candidate.category]}</p>
    <h4 className="mt-2 break-words font-serif text-3xl leading-tight">{candidate.designation}</h4>
    <dl className="mt-5 divide-y divide-[#ded9cf] text-sm">
      <div className="flex flex-wrap justify-between gap-2 py-3"><dt className="text-[#746e66]">Различительная способность</dt><dd className="font-semibold">{distinctivenessLabels[candidate.distinctiveness]}</dd></div>
      <div className="flex flex-wrap justify-between gap-2 py-3"><dt className="text-[#746e66]">Риск описательности</dt><dd className="font-semibold">{descriptionRiskLabels[candidate.description_risk]}</dd></div>
    </dl>
    <p className="mt-4 text-sm leading-6">{candidate.goods_relation}</p>
    <p className="mt-3 text-sm leading-6 text-[#746e66]">{candidate.reasoning}</p>
    {candidate.strengths.length > 0 && <div className="mt-5"><p className="text-sm font-semibold">Сильные стороны</p><ul className="mt-2 list-disc space-y-2 pl-5 text-sm leading-6 text-[#746e66]">{candidate.strengths.map((item, index) => <li key={index}>{item}</li>)}</ul></div>}
    {candidate.risks.length > 0 && <div className="mt-5"><p className="text-sm font-semibold">На что обратить внимание</p><ul className="mt-2 list-disc space-y-2 pl-5 text-sm leading-6 text-[#746e66]">{candidate.risks.map((item, index) => <li key={index}>{item}</li>)}</ul></div>}
  </article>;
}

export function TrademarkComparison() {
  const id = useId();
  const firstRef = useRef<HTMLInputElement>(null);
  const secondRef = useRef<HTMLInputElement>(null);
  const goodsRef = useRef<HTMLTextAreaElement>(null);
  const [first, setFirst] = useState("");
  const [second, setSecond] = useState("");
  const [goods, setGoods] = useState("");
  const [snapshot, setSnapshot] = useState<ChoiceSnapshot | null>(null);
  const [busy, setBusy] = useState(false);
  const submitting = useRef(false);
  const [error, setError] = useState("");
  const [invalidField, setInvalidField] = useState<keyof ChoiceInput | null>(null);
  const [status, setStatus] = useState("");
  const input = { first, second, goods };
  const result = snapshot?.result;
  const stale = !!snapshot && choiceIsStale(input, snapshot.input);

  function updateField(setter: (value: string) => void, value: string) {
    setter(value); setError(""); setInvalidField(null); setStatus("");
  }
  function example() {
    setFirst("Яблоневый сад"); setSecond("Я-ко"); setGoods("Магазин фруктов");
    setError(""); setInvalidField(null); setStatus(""); setSnapshot(null);
    firstRef.current?.focus();
  }
  async function compare(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (submitting.current) return;
    setError(""); setStatus(""); setInvalidField(null);
    let request: ChoiceInput;
    try { request = validateChoiceInput(input); }
    catch (cause) {
      if (cause instanceof ChoiceInputError) {
        setInvalidField(cause.field); setError(cause.message);
        ({ first: firstRef, second: secondRef, goods: goodsRef })[cause.field].current?.focus();
      }
      return;
    }
    submitting.current = true; setBusy(true);
    try {
      const response = markChoiceSchema.parse(await api.post<unknown>("/tools/compare-marks", request));
      if (response.first.designation !== request.first || response.second.designation !== request.second) throw new Error("Unexpected designations");
      setSnapshot({ input: request, result: response });
      setStatus(response.mode === "demo" ? "Демонстрационный пример готов." : "Сравнение готово.");
    } catch (cause) {
      setError(cause instanceof ApiError ? choiceServiceError(cause.status, cause.detail, cause.message) : "Не удалось получить надёжный результат. Попробуйте ещё раз позже.");
    } finally { submitting.current = false; setBusy(false); }
  }
  async function copy() {
    if (!snapshot || stale || busy) return;
    try {
      await navigator.clipboard.writeText(markChoiceReport(snapshot.result, snapshot.input));
      setStatus("Результат скопирован.");
    } catch { setStatus("Не удалось скопировать. Скачайте результат в TXT."); }
  }
  function download() {
    if (!snapshot || stale || busy) return;
    const blob = new Blob(["\ufeff", markChoiceReport(snapshot.result, snapshot.input)], { type: "text/plain;charset=utf-8" });
    const url = URL.createObjectURL(blob);
    const link = document.createElement("a");
    link.href = url; link.download = "registr-vybor-oboznacheniya.txt";
    document.body.append(link); link.click(); link.remove();
    window.setTimeout(() => URL.revokeObjectURL(url), 1500);
    setStatus("Файл TXT подготовлен.");
  }

  return <div className="space-y-7 text-[#38322e]">
    <form onSubmit={compare} noValidate aria-label="Выбор названия для регистрации" aria-busy={busy} className="grid gap-5 rounded-3xl border border-[#ded9cf] bg-white p-5 sm:grid-cols-2 sm:p-7">
      {[
        { field: "first" as const, label: "Первое обозначение", value: first, setter: setFirst, ref: firstRef, placeholder: "Например, Яблоневый сад" },
        { field: "second" as const, label: "Второе обозначение", value: second, setter: setSecond, ref: secondRef, placeholder: "Например, Я-ко" },
      ].map(item => <div key={item.field} className="min-w-0 space-y-2">
        <Label htmlFor={`${id}-${item.field}`}>{item.label}</Label>
        <Input id={`${id}-${item.field}`} ref={item.ref} value={item.value} onChange={event => updateField(item.setter, event.target.value)} placeholder={item.placeholder} required disabled={busy} maxLength={CHOICE_NAME_LIMIT * 2} autoComplete="off" aria-invalid={invalidField === item.field || choiceLength(item.value) > CHOICE_NAME_LIMIT} aria-describedby={`${id}-${item.field}-hint${invalidField === item.field ? ` ${id}-error` : ""}`} className="h-12 rounded-xl border-[#ded9cf] bg-[#fcfbf8] text-base" />
        <p id={`${id}-${item.field}-hint`} className="text-xs text-[#746e66]">{choiceLength(item.value)} / {CHOICE_NAME_LIMIT} символов</p>
      </div>)}
      <div className="space-y-2 sm:col-span-2">
        <Label htmlFor={`${id}-goods`}>Для каких товаров или услуг выбираете название?</Label>
        <Textarea id={`${id}-goods`} ref={goodsRef} value={goods} onChange={event => updateField(setGoods, event.target.value)} required disabled={busy} maxLength={CHOICE_GOODS_LIMIT} placeholder="Например, магазин фруктов" aria-invalid={invalidField === "goods"} aria-describedby={`${id}-goods-hint${invalidField === "goods" ? ` ${id}-error` : ""}`} className="min-h-24 rounded-xl border-[#ded9cf] bg-[#fcfbf8] text-base" />
        <p id={`${id}-goods-hint`} className="text-xs leading-5 text-[#746e66]">Достаточно коротко описать бизнес. Одно и то же слово может подходить для одной сферы и описывать товары в другой.</p>
      </div>
      {error && <p id={`${id}-error`} role="alert" className="text-sm text-red-700 sm:col-span-2">{error}</p>}
      <div className="flex flex-wrap items-center gap-3 sm:col-span-2">
        <Button type="submit" disabled={busy} className="min-h-12 rounded-full bg-[#584b41] px-6 text-white hover:bg-[#483d34]">{busy ? <><Loader2 className="animate-spin" aria-hidden="true" />Оцениваем названия…</> : <>{stale ? "Обновить сравнение" : "Сравнить для регистрации"}<ArrowRight aria-hidden="true" /></>}</Button>
        <Button type="button" variant="ghost" disabled={busy} onClick={example} className="rounded-full text-[#746e66]">Попробовать пример</Button>
      </div>
      {busy && <p role="status" className="text-sm leading-6 text-[#746e66] sm:col-span-2">Проверяем смысл названий, связь с вашим бизнесом и риск описательности. Обычно это занимает до минуты.</p>}
    </form>

    {!result ? <div className="flex items-start gap-4 rounded-2xl bg-[#f4f1eb] p-5 text-sm leading-6 text-[#746e66]"><Scale className="mt-1 h-6 w-6 shrink-0 text-[#9b8258]" aria-hidden="true" /><p>Получите предварительный выбор с объяснением: какое название обладает большей различительной способностью и что стоит проверить перед подачей.</p></div>
      : <section aria-labelledby={`${id}-result-title`} className="space-y-5">
        {stale && <p role="status" className="rounded-xl bg-[#f4eddf] p-4 text-sm text-[#665233]">Названия или сфера изменились. Ниже показана прежняя оценка — обновите сравнение.</p>}
        <div className="rounded-3xl border border-[#ded9cf] bg-[#f4f1eb] p-5 sm:p-7">
          <p className="text-xs font-semibold uppercase tracking-[.12em] text-[#746e66]">{result.mode === "demo" ? "Демонстрационный пример" : "Предварительный выбор"}</p>
          <h3 id={`${id}-result-title`} className="mt-3 break-words font-serif text-3xl leading-tight sm:text-4xl">{choiceHeading(result)}</h3>
          <p className="mt-4 text-sm leading-7">{result.summary}</p>
          <p className="mt-4 text-xs leading-5 text-[#746e66]">Сфера: {snapshot?.input.goods}</p>
          {result.mode === "demo" && <p className="mt-3 text-xs leading-5 text-[#746e66]">Это подготовленный пример. В рабочем режиме сервис анализирует введённые варианты с помощью подключённой модели.</p>}
        </div>
        <div className="grid items-start gap-5 lg:grid-cols-2"><CandidateCard candidate={result.first} preferred={result.recommended === "first"} /><CandidateCard candidate={result.second} preferred={result.recommended === "second"} /></div>
        <div className="rounded-2xl border border-[#ded9cf] bg-white p-5 sm:p-6"><h4 className="font-serif text-2xl">Что сделать дальше</h4><ol className="mt-4 list-decimal space-y-2 pl-5 text-sm leading-6 text-[#746e66]">{result.next_steps.map((step, index) => <li key={index}>{step}</li>)}</ol></div>
        <details className="rounded-2xl border border-[#ded9cf] bg-white p-5 text-sm leading-6"><summary className="cursor-pointer font-medium">Основания и границы оценки</summary><ul className="mt-4 list-disc space-y-2 pl-5 text-[#746e66]">{result.limitations.map((item, index) => <li key={index}>{item}</li>)}</ul><ul className="mt-4 space-y-2">{result.sources.map(source => <li key={source.url}><a href={source.url} target="_blank" rel="noopener noreferrer" className="text-[#7c643e] underline underline-offset-4">{source.title}</a></li>)}</ul></details>
        <div className="flex flex-wrap gap-2"><Button type="button" variant="outline" onClick={copy} disabled={stale || busy} className="rounded-full"><Copy aria-hidden="true" />Копировать</Button><Button type="button" variant="outline" onClick={download} disabled={stale || busy} className="rounded-full"><Download aria-hidden="true" />Скачать TXT</Button></div>
      </section>}
    <p className="text-xs leading-6 text-[#746e66]">Сравниваем сами названия в указанной сфере. Поиск похожих зарегистрированных знаков и заявок — отдельный следующий шаг; итоговое решение принимает Роспатент.</p>
    <p role="status" className="text-xs leading-5 text-[#746e66]">{status}</p>
  </div>;
}
