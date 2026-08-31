import { useEffect, useRef, useState } from "react";
import { AlertCircle, CheckCircle2, Download, FileText, Loader2, Paperclip, Sparkles, Upload } from "lucide-react";
import { api, ApiError, type SourceDocumentDto } from "@/lib/api";
import { Button } from "@/components/ui/button";
import { Checkbox } from "@/components/ui/checkbox";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import { useToast } from "@/hooks/use-toast";

interface FactItem { criterion: string; label: string; help: string; confirmed: boolean; fact: string; document_ids: number[]; }
interface OfficeActionDto {
  id: number; notice_document_id: number; notice_filename: string | null; status: string;
  response_deadline: string | null; homogeneity_facts: FactItem[]; distinctiveness_evidence: FactItem[];
  additional_facts: string; notice_summary: string | null; response_summary: string | null;
  missing_evidence: string[]; draft_text: string | null;
}

const makeFacts = (items: string[][]): FactItem[] => items.map(([criterion, label, help]) => ({ criterion, label, help, confirmed: false, fact: "", document_ids: [] }));
const HOMOGENEITY = makeFacts([
  ["purpose", "Назначение", "Для какой задачи покупают товары или услуги"],
  ["nature", "Природа товара или услуги", "Что это по существу: продукт, материал, услуга или технология"],
  ["material", "Материал", "Из чего изготовлены товары"],
  ["consumers", "Покупатели", "Кто обычно приобретает товары или услуги"],
  ["distribution_channels", "Где продаётся", "Магазины, маркетплейсы, профессиональные или иные каналы"],
  ["interchangeability", "Взаимозаменяемость", "Может ли один товар заменить другой"],
  ["joint_use", "Совместное использование", "Используются ли товары или услуги вместе"],
  ["common_origin", "Обычный производитель", "Ожидает ли покупатель, что такие товары выпускает одна компания"],
]);
const DISTINCTIVENESS = makeFacts([
  ["first_use_date", "Когда начали использовать знак", "Укажите дату или период первого использования"],
  ["sales_territory", "География продаж", "Города, регионы или страны, где использовался знак"],
  ["revenue_and_sales", "Выручка и объём продаж", "Конкретные периоды и показатели"],
  ["advertising_expenses", "Расходы на рекламу", "Суммы, периоды и рекламные каналы"],
  ["media_publications", "Публикации в СМИ", "Статьи, обзоры и упоминания"],
  ["contracts_and_catalogs", "Договоры и каталоги", "Материалы, где знак связан с товарами или услугами"],
  ["website_marketplace_stats", "Сайт и маркетплейсы", "Посещаемость, заказы, отзывы и карточки товаров"],
  ["surveys", "Опросы потребителей", "Исследования узнаваемости обозначения"],
  ["product_packaging_photos", "Фото товара и упаковки", "Изображения реального использования знака"],
]);
const mergeFacts = (template: FactItem[], saved: FactItem[]) => template.map((item) => ({ ...item, ...(saved.find((value) => value.criterion === item.criterion) || {}) }));
const errorMessage = (error: unknown) => error instanceof ApiError ? error.message : "Попробуйте ещё раз";

export function OfficeActionResponse({ appId, audience = "client" }: { appId: number; audience?: "client" | "professional" }) {
  const { toast } = useToast();
  const noticeInput = useRef<HTMLInputElement>(null);
  const [item, setItem] = useState<OfficeActionDto | null>(null);
  const [notice, setNotice] = useState<SourceDocumentDto | null>(null);
  const [deadline, setDeadline] = useState("");
  const [homogeneity, setHomogeneity] = useState<FactItem[]>(HOMOGENEITY);
  const [distinctiveness, setDistinctiveness] = useState<FactItem[]>(DISTINCTIVENESS);
  const [additionalFacts, setAdditionalFacts] = useState("");
  const [documents, setDocuments] = useState<Record<number, SourceDocumentDto>>({});
  const [loading, setLoading] = useState(true);
  const [uploading, setUploading] = useState(false);
  const [saving, setSaving] = useState(false);
  const [generating, setGenerating] = useState(false);
  const [autosaveStatus, setAutosaveStatus] = useState<"idle" | "dirty" | "saving" | "saved" | "error">("idle");
  const autosaveReady = useRef(false);
  const lastSavedSnapshot = useRef("");

  const applyItem = (value: OfficeActionDto) => {
    setItem(value); setDeadline(value.response_deadline || "");
    setHomogeneity(mergeFacts(HOMOGENEITY, value.homogeneity_facts));
    setDistinctiveness(mergeFacts(DISTINCTIVENESS, value.distinctiveness_evidence));
    setAdditionalFacts(value.additional_facts || "");
  };
  const startNew = () => {
    setItem(null); setNotice(null); setDeadline(""); setAdditionalFacts("");
    setHomogeneity(HOMOGENEITY); setDistinctiveness(DISTINCTIVENESS);
    autosaveReady.current = false; lastSavedSnapshot.current = ""; setAutosaveStatus("idle");
  };

  useEffect(() => {
    autosaveReady.current = false;
    lastSavedSnapshot.current = "";
    Promise.all([
      api.get<{ items: OfficeActionDto[] }>(`/applications/${appId}/office-actions`),
      api.get<{ items: SourceDocumentDto[] }>(`/applications/${appId}/source-documents`),
    ]).then(([actions, files]) => {
      setDocuments(Object.fromEntries(files.items.map((file) => [file.id, file])));
      if (actions.items[0]) { applyItem(actions.items[0]); setNotice(files.items.find((file) => file.id === actions.items[0].notice_document_id) || null); }
    }).catch((error) => toast({ title: "Не удалось открыть переписку", description: errorMessage(error), variant: "destructive" })).finally(() => setLoading(false));
  }, [appId]);

  const draftSnapshot = JSON.stringify({
    noticeId: notice?.id || null,
    deadline,
    homogeneity,
    distinctiveness,
    additionalFacts,
  });

  useEffect(() => {
    if (loading || !notice) return;
    if (!autosaveReady.current) {
      autosaveReady.current = true;
      lastSavedSnapshot.current = draftSnapshot;
      return;
    }
    if (draftSnapshot === lastSavedSnapshot.current) return;
    setAutosaveStatus("dirty");
    const timer = window.setTimeout(async () => {
      setAutosaveStatus("saving");
      const payload = {
        notice_document_id: notice.id,
        response_deadline: deadline || null,
        homogeneity_facts: homogeneity,
        distinctiveness_evidence: distinctiveness,
        additional_facts: additionalFacts || null,
      };
      try {
        const saved = item
          ? await api.put<OfficeActionDto>(`/applications/${appId}/office-actions/${item.id}`, payload)
          : await api.post<OfficeActionDto>(`/applications/${appId}/office-actions`, payload);
        setItem(saved);
        lastSavedSnapshot.current = draftSnapshot;
        setAutosaveStatus("saved");
      } catch {
        setAutosaveStatus("error");
      }
    }, 900);
    return () => window.clearTimeout(timer);
  }, [appId, loading, notice?.id, item?.id, draftSnapshot]);

  const uploadNotice = async (file?: File) => {
    if (!file) return; setUploading(true);
    try {
      const uploaded = await api.upload<SourceDocumentDto>(`/applications/${appId}/source-documents`, file);
      setNotice(uploaded); setDocuments((old) => ({ ...old, [uploaded.id]: uploaded }));
      toast({ title: "Уведомление загружено", description: "Теперь добавьте известные вам факты и доказательства." });
    } catch (error) { toast({ title: "Не удалось загрузить уведомление", description: errorMessage(error), variant: "destructive" }); }
    finally { setUploading(false); if (noticeInput.current) noticeInput.current.value = ""; }
  };

  const updateFact = (group: "homogeneity" | "distinctiveness", criterion: string, changes: Partial<FactItem>) => {
    const setter = group === "homogeneity" ? setHomogeneity : setDistinctiveness;
    setter((old) => old.map((fact) => fact.criterion === criterion ? { ...fact, ...changes } : fact));
  };
  const uploadEvidence = async (group: "homogeneity" | "distinctiveness", criterion: string, file?: File) => {
    if (!file) return; setUploading(true);
    try {
      const uploaded = await api.upload<SourceDocumentDto>(`/applications/${appId}/source-documents`, file);
      setDocuments((old) => ({ ...old, [uploaded.id]: uploaded }));
      const source = group === "homogeneity" ? homogeneity : distinctiveness;
      const fact = source.find((value) => value.criterion === criterion)!;
      updateFact(group, criterion, { document_ids: [...fact.document_ids, uploaded.id] });
      toast({ title: "Доказательство приложено" });
    } catch (error) { toast({ title: "Не удалось приложить файл", description: errorMessage(error), variant: "destructive" }); }
    finally { setUploading(false); }
  };

  const save = async (): Promise<OfficeActionDto | null> => {
    if (!notice) { toast({ title: "Сначала загрузите уведомление Роспатента", variant: "destructive" }); return null; }
    setSaving(true);
    const payload = { notice_document_id: notice.id, response_deadline: deadline || null, homogeneity_facts: homogeneity, distinctiveness_evidence: distinctiveness, additional_facts: additionalFacts || null };
    try {
      const saved = item ? await api.put<OfficeActionDto>(`/applications/${appId}/office-actions/${item.id}`, payload) : await api.post<OfficeActionDto>(`/applications/${appId}/office-actions`, payload);
      applyItem(saved); lastSavedSnapshot.current = JSON.stringify({ noticeId: notice.id, deadline: saved.response_deadline || "", homogeneity: mergeFacts(HOMOGENEITY, saved.homogeneity_facts), distinctiveness: mergeFacts(DISTINCTIVENESS, saved.distinctiveness_evidence), additionalFacts: saved.additional_facts || "" }); setAutosaveStatus("saved"); toast({ title: "Факты сохранены" }); return saved;
    } catch (error) { toast({ title: "Не удалось сохранить", description: errorMessage(error), variant: "destructive" }); return null; }
    finally { setSaving(false); }
  };
  const generate = async () => {
    const saved = await save(); if (!saved) return; setGenerating(true);
    try {
      const generated = await api.post<OfficeActionDto>(`/applications/${appId}/office-actions/${saved.id}/generate`);
      applyItem(generated); toast({ title: "Черновик ответа подготовлен", description: "Проверьте текст и список недостающих доказательств." });
    } catch (error) { toast({ title: "Не удалось подготовить ответ", description: errorMessage(error), variant: "destructive" }); }
    finally { setGenerating(false); }
  };

  if (loading) return <div className="flex min-h-48 items-center justify-center text-[#6d6d7d]"><Loader2 className="mr-2 h-5 w-5 animate-spin" />Загружаем переписку…</div>;
  const professional = audience === "professional";
  return <div>
    <p className="text-sm font-bold uppercase tracking-[0.14em] text-[#0d9f9b]">После подачи заявки</p>
    <h2 className="mt-2 text-3xl font-semibold text-[#11113f]">{professional ? "Переписка с Роспатентом" : "Ответить Роспатенту"}</h2>
    <p className="mt-3 max-w-3xl leading-relaxed text-[#6d6d7d]">{professional ? "Загрузите уведомление, проверьте сведения клиента и доказательства. Система подготовит рабочий черновик, который необходимо юридически проверить перед отправкой." : "Загрузите уведомление и сообщите только те обстоятельства, которые можете подтвердить. Система объяснит замечания и подготовит редактируемый черновик ответа."}</p>
    <section className="mt-8 rounded-2xl border border-[#11113f]/10 bg-[#f8f8f6] p-5">
      <div className="flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between"><div><h3 className="font-semibold text-[#11113f]">1. Уведомление Роспатента</h3><p className="mt-1 text-sm text-[#6d6d7d]">Подойдёт PDF, DOCX, TXT или читаемый скан.</p></div><input ref={noticeInput} type="file" className="hidden" accept=".pdf,.docx,.txt,.png,.jpg,.jpeg" onChange={(event) => uploadNotice(event.target.files?.[0])} /><div className="flex flex-wrap gap-2">{item && <Button variant="ghost" onClick={startNew}>Новое уведомление</Button>}<Button variant="outline" onClick={() => noticeInput.current?.click()} disabled={uploading}><Upload className="mr-2 h-4 w-4" />{notice ? "Заменить файл" : "Загрузить уведомление"}</Button></div></div>
      {notice && <div className="mt-4 flex items-center gap-3 rounded-xl bg-white p-4 text-sm"><FileText className="h-5 w-5 text-[#0d9f9b]" /><span className="font-medium">{notice.original_filename}</span><CheckCircle2 className="ml-auto h-5 w-5 text-emerald-600" /></div>}
      <div className="mt-4 max-w-xs"><Label htmlFor="office-deadline">Срок ответа, если указан</Label><Input id="office-deadline" type="date" className="mt-2" value={deadline} onChange={(event) => setDeadline(event.target.value)} /></div>
    </section>
    <FactGroup title={professional ? "2. Факторы однородности товаров и услуг" : "2. Почему товары или услуги отличаются"} description="Отметьте только подходящие пункты. Сам номер класса МКТУ не доказывает, что товары однородны." items={homogeneity} group="homogeneity" documents={documents} onChange={updateFact} onUpload={uploadEvidence} />
    <FactGroup title={professional ? "3. Доказательства приобретённой различительной способности" : "3. Как знак стал узнаваемым"} description="Этот блок нужен, если обозначение использовалось до подачи заявки. Добавьте конкретные даты, показатели и материалы." items={distinctiveness} group="distinctiveness" documents={documents} onChange={updateFact} onUpload={uploadEvidence} />
    <section className="mt-6 rounded-2xl border border-[#11113f]/10 p-5"><Label htmlFor="additional-facts" className="text-base font-semibold">Другие важные обстоятельства</Label><p className="mt-1 text-sm text-[#6d6d7d]">Не добавляйте предположения. Напишите, откуда вам известен факт.</p><Textarea id="additional-facts" className="mt-3 min-h-24" value={additionalFacts} onChange={(event) => setAdditionalFacts(event.target.value)} placeholder="Например: знак используется с мая 2022 года; подтверждается договором и карточкой товара…" /></section>
    <div className="mt-7 flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between"><p className={`text-xs font-medium ${autosaveStatus === "error" ? "text-red-700" : "text-[#087c78]"}`}>{autosaveStatus === "dirty" ? "Есть несохранённые изменения…" : autosaveStatus === "saving" ? "Сохраняем черновик…" : autosaveStatus === "saved" ? "✓ Черновик сохранён автоматически" : autosaveStatus === "error" ? "Автосохранение не сработало — нажмите «Сохранить факты»" : notice ? "Изменения будут сохраняться автоматически" : ""}</p><div className="flex flex-wrap justify-end gap-3"><Button variant="outline" onClick={save} disabled={saving || generating || autosaveStatus === "saving"}>{saving && <Loader2 className="mr-2 h-4 w-4 animate-spin" />}Сохранить факты</Button><Button className="bg-[#0d9f9b] hover:bg-[#087c78]" onClick={generate} disabled={saving || generating || autosaveStatus === "saving" || !notice}>{generating ? <Loader2 className="mr-2 h-4 w-4 animate-spin" /> : <Sparkles className="mr-2 h-4 w-4" />}Подготовить черновик ответа</Button></div></div>
    {item?.draft_text && <section className="mt-8 rounded-2xl border border-emerald-200 bg-emerald-50/50 p-5 sm:p-6"><div className="flex flex-col gap-4 sm:flex-row sm:items-start sm:justify-between"><div><p className="text-xs font-bold uppercase tracking-wider text-emerald-700">Черновик готов</p><h3 className="mt-1 text-xl font-semibold text-[#11113f]">{item.response_summary}</h3></div><Button onClick={() => api.download(`/applications/${appId}/office-actions/${item.id}/download`, `otvet-rospatent-${appId}.docx`)}><Download className="mr-2 h-4 w-4" />Скачать DOCX</Button></div>{item.notice_summary && <div className="mt-5 rounded-xl bg-white p-4"><p className="font-semibold">Что требует Роспатент</p><p className="mt-2 whitespace-pre-line text-sm leading-relaxed text-[#55556b]">{item.notice_summary}</p></div>}{item.missing_evidence.length > 0 && <div className="mt-4 rounded-xl border border-amber-200 bg-amber-50 p-4"><p className="flex items-center gap-2 font-semibold text-amber-900"><AlertCircle className="h-4 w-4" />Чего ещё не хватает</p><ul className="mt-2 space-y-1 pl-5 text-sm text-amber-900">{item.missing_evidence.map((value) => <li key={value} className="list-disc">{value}</li>)}</ul></div>}<details className="mt-4 rounded-xl bg-white p-4"><summary className="cursor-pointer font-semibold">Показать текст черновика</summary><div className="mt-4 whitespace-pre-line text-sm leading-relaxed text-[#3f3f55]">{item.draft_text}</div></details></section>}
  </div>;
}

function FactGroup({ title, description, items, group, documents, onChange, onUpload }: { title: string; description: string; items: FactItem[]; group: "homogeneity" | "distinctiveness"; documents: Record<number, SourceDocumentDto>; onChange: (group: "homogeneity" | "distinctiveness", criterion: string, changes: Partial<FactItem>) => void; onUpload: (group: "homogeneity" | "distinctiveness", criterion: string, file?: File) => void }) {
  return <section className="mt-6 rounded-2xl border border-[#11113f]/10 p-5 sm:p-6"><h3 className="text-lg font-semibold text-[#11113f]">{title}</h3><p className="mt-1 text-sm text-[#6d6d7d]">{description}</p><div className="mt-5 grid gap-3 lg:grid-cols-2">{items.map((fact) => <div key={fact.criterion} className={`rounded-xl border p-4 ${fact.confirmed ? "border-[#0d9f9b]/40 bg-[#eef9f8]" : "border-[#11113f]/10"}`}><div className="flex items-start gap-3"><Checkbox id={`${group}-${fact.criterion}`} checked={fact.confirmed} onCheckedChange={(checked) => onChange(group, fact.criterion, { confirmed: checked === true })} /><label htmlFor={`${group}-${fact.criterion}`} className="cursor-pointer"><span className="block font-semibold text-[#11113f]">{fact.label}</span><span className="mt-1 block text-sm text-[#6d6d7d]">{fact.help}</span></label></div>{fact.confirmed && <div className="mt-4 pl-7"><Textarea value={fact.fact} onChange={(event) => onChange(group, fact.criterion, { fact: event.target.value })} placeholder="Опишите конкретный факт: что, когда, где и в каком объёме" className="min-h-20 bg-white" /><label className="mt-3 inline-flex cursor-pointer items-center text-sm font-semibold text-[#087c78]"><Paperclip className="mr-2 h-4 w-4" />Приложить подтверждение<input type="file" className="hidden" onChange={(event) => onUpload(group, fact.criterion, event.target.files?.[0])} /></label>{fact.document_ids.length > 0 && <div className="mt-2 space-y-1">{fact.document_ids.map((id) => <p key={id} className="truncate text-xs text-[#6d6d7d]">✓ {documents[id]?.original_filename || `Файл №${id}`}</p>)}</div>}</div>}</div>)}</div></section>;
}
