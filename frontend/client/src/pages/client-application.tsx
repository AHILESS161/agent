import { useEffect, useMemo, useState } from "react";
import { useLocation, useParams } from "wouter";
import {
  AlertCircle,
  ArrowLeft,
  Check,
  CheckCircle2,
  ChevronRight,
  Circle,
  Loader2,
  PencilLine,
  Play,
  ShieldAlert,
  ShieldCheck,
  Sparkles,
  FileSignature,
  FileText,
  LockKeyhole,
  Download,
  ReceiptText,
} from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import { Badge } from "@/components/ui/badge";
import { useToast } from "@/hooks/use-toast";
import { api, ApiError, type ReconciliationDto } from "@/lib/api";
import { useCase } from "@/lib/use-cases";
import { cn } from "@/lib/utils";
import { HelpTip } from "@/components/help-tip";
import { useApi } from "@/lib/use-api";
import { COUNTRY_OPTIONS } from "@/lib/country-codes";
import { MARK_TYPE_LABELS, type MarkType } from "@shared/schema";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";

type Section = "data" | "check" | "result";

interface ClassSuggestion {
  id: number;
  class_number: number;
  class_description: string | null;
  rationale: string | null;
  approved: boolean | null;
}

interface RiskReport {
  overall_risk: "low" | "medium" | "high" | "critical" | null;
  is_complete: boolean;
  incomplete_checks?: string[];
  sections: Record<string, {
    findings?: Array<{ description: string; recommendation?: string; level?: string }>;
    is_inconclusive?: boolean;
    inconclusive_reason?: string | null;
  } | null>;
}

interface Recommendation {
  summary: string | null;
  risk_assessment: string | null;
  recommended_action: string | null;
  key_risks_json: string[] | null;
}

const SECTION_META: Array<{ id: Section; label: string; icon: typeof Circle }> = [
  { id: "data", label: "Данные", icon: PencilLine },
  { id: "check", label: "Проверка", icon: Sparkles },
  { id: "result", label: "Результат", icon: ShieldCheck },
];

const ACTION_LABELS: Record<string, string> = {
  proceed: "Можно переходить к подготовке заявления",
  modify: "Сначала измените обозначение или перечень товаров и услуг",
  withdraw: "Не подавайте обозначение в текущем виде",
  further_review: "Завершите проверку перед подачей",
};

function messageOf(error: unknown, fallback: string) {
  return error instanceof ApiError ? error.message : fallback;
}

export default function ClientApplicationPage() {
  const params = useParams<{ id: string }>();
  const appId = Number(params.id);
  const [, setLocation] = useLocation();
  const current = useCase(appId);
  const [section, setSection] = useState<Section>("data");
  const [draftRequest, setDraftRequest] = useState(0);

  if (current.isLoading) {
    return <div className="flex min-h-[55vh] items-center justify-center text-[#6d6d7d]"><Loader2 className="mr-2 h-5 w-5 animate-spin" /> Загружаем заявку…</div>;
  }

  if (current.error || !current.data) {
    return (
      <div className="mx-auto max-w-xl rounded-[1.5rem] border border-red-200 bg-white p-8 text-center">
        <AlertCircle className="mx-auto h-8 w-8 text-red-500" />
        <h1 className="mt-4 text-2xl font-semibold">Заявка не открылась</h1>
        <p className="mt-2 text-[#6d6d7d]">{current.error || "Заявка не найдена"}</p>
        <Button variant="outline" className="mt-5 rounded-full" onClick={() => setLocation("/dashboard")}>К моим заявкам</Button>
      </div>
    );
  }

  const { application, client } = current.data;

  return (
    <div className="space-y-7">
      <button type="button" onClick={() => setLocation("/dashboard")} className="flex items-center gap-2 text-sm font-semibold text-[#6d6d7d] hover:text-[#11113f]">
        <ArrowLeft className="h-4 w-4" /> Все заявки
      </button>

      <section className="rounded-[1.8rem] bg-[#11113f] px-6 py-7 text-white sm:px-9">
        <div className="flex flex-col gap-5 sm:flex-row sm:items-center sm:justify-between">
          <div>
            <p className="text-xs font-bold uppercase tracking-[0.16em] text-[#43c7c2]">Заявка №{application.id}</p>
            <h1 className="mt-2 text-3xl font-semibold sm:text-4xl">{application.markName}</h1>
            <p className="mt-2 text-sm text-white/60">Можно вернуться позже — введённые данные сохраняются</p>
          </div>
          <div className="flex w-fit flex-col items-start gap-2 sm:items-end">
            <span className="inline-flex items-center gap-2 rounded-full bg-white/10 px-4 py-2 text-sm font-semibold">
              <span className="h-2 w-2 rounded-full bg-[#43c7c2]" /> Заявка заполняется
            </span>
            <button type="button" onClick={() => { setDraftRequest((value) => value + 1); setSection("result"); }} className="text-sm font-semibold text-[#43c7c2] underline decoration-[#43c7c2]/40 underline-offset-4 hover:text-white">
              Открыть черновик заявления →
            </button>
          </div>
        </div>
      </section>

      <nav className="grid grid-cols-3 gap-2 rounded-[1.3rem] border border-[#11113f]/10 bg-white p-2">
        {SECTION_META.map((item, index) => {
          const active = section === item.id;
          return (
            <button
              key={item.id}
              type="button"
              onClick={() => setSection(item.id)}
              className={cn(
                "flex min-h-14 items-center gap-3 rounded-xl px-3 text-left text-sm font-semibold transition-colors",
                active ? "bg-[#e9f7f6] text-[#087c78]" : "text-[#66667a] hover:bg-[#f6f5f1] hover:text-[#11113f]",
              )}
            >
              <span className={cn("flex h-8 w-8 shrink-0 items-center justify-center rounded-full border text-xs", active ? "border-[#0d9f9b] bg-[#0d9f9b] text-white" : "border-[#11113f]/15")}>{index + 1}</span>
              {item.label}
            </button>
          );
        })}
      </nav>

      <div className="rounded-[1.8rem] border border-[#11113f]/10 bg-white p-5 shadow-[0_14px_45px_rgba(21,21,55,0.05)] sm:p-8 lg:p-10">
        {section === "data" && <ClientDataForm application={application} client={client} onSaved={current.reload} onNext={() => setSection("check")} />}
        {section === "check" && <ClientCheck appId={appId} onResult={() => setSection("result")} />}
        {section === "result" && <ClientResult appId={appId} draftRequest={draftRequest} onEditData={() => setSection("data")} />}
      </div>
    </div>
  );
}

function ClientPanel({ title, description, children }: { title: string; description: string; children: React.ReactNode }) {
  return (
    <div>
      <p className="text-sm font-bold uppercase tracking-[0.14em] text-[#0d9f9b]">Товарный знак</p>
      <h2 className="mt-2 text-3xl font-semibold text-[#11113f]">{title}</h2>
      <p className="mt-3 max-w-3xl leading-relaxed text-[#6d6d7d]">{description}</p>
      <div className="mt-8">{children}</div>
    </div>
  );
}

function ClientDataForm({ application, client, onSaved, onNext }: { application: any; client: any; onSaved: () => void; onNext: () => void }) {
  const { toast } = useToast();
  const [saving, setSaving] = useState(false);
  const [form, setForm] = useState({
    name: client?.fullNameOrCompanyName || "",
    inn: client?.inn || "",
    ogrn: client?.ogrnOrOgrnip || "",
    address: client?.address || "",
    country: client?.countryCode || "RU",
    email: client?.email || "",
    phone: client?.phone || "",
    markName: application.markName || "",
    markType: application.markType as MarkType,
    business: application.businessDescription || "",
    goods: application.goodsServicesRaw || "",
    description: application.descriptionOfMark || "",
    colors: application.colorsClaimed || "",
    transliteration: application.transliteration || "",
    translation: application.translation || "",
  });

  const set = (key: keyof typeof form, value: string) => setForm((old) => ({ ...old, [key]: value }));

  const save = async () => {
    if (!form.name.trim() || !form.markName.trim()) {
      toast({ title: "Заполните обязательные поля", description: "Нужны заявитель и обозначение.", variant: "destructive" });
      return;
    }
    setSaving(true);
    try {
      await Promise.all([
        client ? api.put(`/clients/${client.id}`, {
          full_name_or_company_name: form.name.trim(), inn: form.inn.trim() || null,
          ogrn_or_ogrnip: form.ogrn.trim() || null, address: form.address.trim() || null,
          country: form.country || "RU", email: form.email.trim() || null, phone: form.phone.trim() || null,
        }) : Promise.resolve(),
        api.put(`/applications/${application.id}`, {
          mark_name: form.markName.trim(), mark_text: form.markName.trim(), mark_type: form.markType,
          business_description: form.business.trim() || null, goods_services_raw: form.goods.trim() || null,
          description_of_mark: form.description.trim() || null, colors_claimed: form.colors.trim() || null,
          transliteration: form.transliteration.trim() || null, translation: form.translation.trim() || null,
        }),
      ]);
      toast({ title: "Данные сохранены" });
      onSaved();
      onNext();
    } catch (error) {
      toast({ title: "Не удалось сохранить", description: messageOf(error, "Попробуйте ещё раз"), variant: "destructive" });
    } finally { setSaving(false); }
  };

  return (
    <ClientPanel title="Проверьте основные данные" description="Поля с пометкой «вручную» нужно заполнить вам. Если реквизиты были найдены в выписке, они уже подставлены — достаточно проверить.">
      <div className="grid gap-8 lg:grid-cols-2">
        <FormGroup title={<span className="inline-flex items-center gap-1">О заявителе <HelpTip text="Заявитель — человек, ИП или организация, на имя которых будет зарегистрирован товарный знак. После регистрации именно заявитель станет правообладателем." /></span>} hint="Эти сведения попадут в заявление как данные правообладателя">
          <MarkedField label="Наименование или ФИО" mode="manual"><Input value={form.name} onChange={(e) => set("name", e.target.value)} /></MarkedField>
          <div className="grid gap-4 sm:grid-cols-2">
            <MarkedField label="ИНН" mode={form.inn ? "document" : "manual"}><Input value={form.inn} onChange={(e) => set("inn", e.target.value)} /></MarkedField>
            <MarkedField label="ОГРН / ОГРНИП" mode={form.ogrn ? "document" : "manual"}><Input value={form.ogrn} onChange={(e) => set("ogrn", e.target.value)} /></MarkedField>
          </div>
          <MarkedField label="Адрес" mode={form.address ? "document" : "manual"}><Input value={form.address} onChange={(e) => set("address", e.target.value)} /></MarkedField>
          <MarkedField label={<span className="inline-flex items-center gap-1">Код страны <HelpTip text="Двухбуквенный код страны заявителя по стандарту ВОИС ST.3. Для заявителей из России используется RU." /></span>} mode="manual">
            <select value={form.country} onChange={(event) => set("country", event.target.value)} className="flex h-10 w-full rounded-md border border-input bg-background px-3 py-2 text-sm ring-offset-background focus:outline-none focus:ring-2 focus:ring-ring focus:ring-offset-2">
              {COUNTRY_OPTIONS.map((country) => <option key={country.code} value={country.code}>{country.name} — {country.code}</option>)}
            </select>
          </MarkedField>
          <div className="grid gap-4 sm:grid-cols-2">
            <MarkedField label="E-mail для переписки" mode="manual"><Input type="email" value={form.email} onChange={(e) => set("email", e.target.value)} /></MarkedField>
            <MarkedField label="Телефон для переписки" mode="manual"><Input value={form.phone} onChange={(e) => set("phone", e.target.value)} /></MarkedField>
          </div>
          <p className="text-xs leading-relaxed text-[#6d6d7d]">Адрес, телефон и e-mail будут использованы в черновике как контакты для переписки с Роспатентом.</p>
        </FormGroup>

        <FormGroup title="О товарном знаке" hint="По описанию система предложит классы товаров и услуг и выполнит поиск">
          <MarkedField label={<span className="inline-flex items-center gap-1">Вид знака <HelpTip text="Словесный знак защищает написанное название. Изобразительный — картинку без текста. Комбинированный — название и изображение вместе." /></span>} mode="manual">
            <Select value={form.markType} onValueChange={(value) => set("markType", value)}><SelectTrigger><SelectValue /></SelectTrigger><SelectContent>{(Object.keys(MARK_TYPE_LABELS) as MarkType[]).map((type) => <SelectItem key={type} value={type}>{MARK_TYPE_LABELS[type]}</SelectItem>)}</SelectContent></Select>
          </MarkedField>
          <MarkedField label="Обозначение" mode="manual"><Input value={form.markName} onChange={(e) => set("markName", e.target.value)} /></MarkedField>
          <MarkedField label="Чем вы занимаетесь" mode="manual"><Textarea rows={3} value={form.business} onChange={(e) => set("business", e.target.value)} placeholder="Например: производство одежды и продажа через интернет-магазин" /></MarkedField>
          <MarkedField label={<span className="inline-flex items-center gap-1">Товары и услуги <HelpTip text="Перечислите то, что вы продаёте или делаете под этим названием. Например: одежда, доставка еды, обучение, разработка программ. От этого зависит объём защиты знака." /></span>} mode="manual"><Textarea rows={3} value={form.goods} onChange={(e) => set("goods", e.target.value)} placeholder="Например: одежда, обувь, розничная торговля" /></MarkedField>
          <details className="rounded-xl border border-[#11113f]/10 bg-white p-4">
            <summary className="cursor-pointer font-semibold text-[#11113f]">Дополнительные сведения для заявления</summary>
            <p className="mt-2 text-xs leading-relaxed text-[#6d6d7d]">Заполняйте только применимые поля. Они попадут в предпросмотр и скачиваемый DOCX.</p>
            <div className="mt-4 space-y-4">
              <MarkedField label="Описание обозначения" mode="manual"><Textarea rows={3} value={form.description} onChange={(e) => set("description", e.target.value)} placeholder="Опишите словесные и графические элементы знака" /></MarkedField>
              <MarkedField label="Заявленные цвета" mode="manual"><Input value={form.colors} onChange={(e) => set("colors", e.target.value)} placeholder="Например: тёмно-синий и бирюзовый" /></MarkedField>
              <div className="grid gap-4 sm:grid-cols-2">
                <MarkedField label="Транслитерация" mode="manual"><Input value={form.transliteration} onChange={(e) => set("transliteration", e.target.value)} placeholder="Например: REGISTR" /></MarkedField>
                <MarkedField label="Перевод" mode="manual"><Input value={form.translation} onChange={(e) => set("translation", e.target.value)} placeholder="Если у слова есть перевод" /></MarkedField>
              </div>
            </div>
          </details>
        </FormGroup>
      </div>
      <div className="mt-8 flex justify-end"><Button disabled={saving} onClick={save} className="rounded-full bg-[#0d9f9b] px-7 hover:bg-[#078984]">{saving && <Loader2 className="h-4 w-4 animate-spin" />} Сохранить и продолжить <ChevronRight className="h-4 w-4" /></Button></div>
    </ClientPanel>
  );
}

function FormGroup({ title, hint, children }: { title: React.ReactNode; hint: string; children: React.ReactNode }) {
  return <section className="rounded-[1.3rem] bg-[#f8f7f4] p-5 sm:p-6"><h3 className="text-xl font-semibold">{title}</h3><p className="mt-1 text-sm text-[#6d6d7d]">{hint}</p><div className="mt-6 space-y-5">{children}</div></section>;
}

function MarkedField({ label, mode, children }: { label: React.ReactNode; mode: "manual" | "document"; children: React.ReactNode }) {
  return <div><div className="mb-2 flex flex-wrap items-center justify-between gap-2"><Label className="text-sm font-semibold">{label}</Label><span className={cn("rounded-full px-2.5 py-1 text-[11px] font-bold", mode === "manual" ? "bg-amber-100 text-amber-800" : "bg-emerald-100 text-emerald-800")}>{mode === "manual" ? "Заполнить вручную" : "Из документа — проверьте"}</span></div>{children}</div>;
}

function ClientCheck({ appId, onResult }: { appId: number; onResult: () => void }) {
  const { toast } = useToast();
  const [reconciliation, setReconciliation] = useState<ReconciliationDto | null>(null);
  const [classes, setClasses] = useState<ClassSuggestion[]>([]);
  const [loading, setLoading] = useState(true);
  const [running, setRunning] = useState(false);
  const [phase, setPhase] = useState(0);

  const phases = [
    "Определяем подходящие классы товаров и услуг",
    "Ищем сходные товарные знаки и заявки",
    "Проверяем возможные основания для отказа",
    "Собираем понятный итог и рекомендации",
  ];

  useEffect(() => {
    if (!running) { setPhase(0); return; }
    const timer = window.setInterval(
      () => setPhase((current) => Math.min(current + 1, phases.length - 1)),
      7000,
    );
    return () => window.clearInterval(timer);
  }, [running]);

  const load = async () => {
    setLoading(true);
    const [fields, classData] = await Promise.all([
      api.get<ReconciliationDto>(`/applications/${appId}/field-reconciliation`).catch(() => null),
      api.get<{ suggestions: ClassSuggestion[] }>(`/applications/${appId}/classes`).catch(() => ({ suggestions: [] })),
    ]);
    setReconciliation(fields); setClasses(classData.suggestions); setLoading(false);
  };
  useEffect(() => { void load(); }, [appId]);

  const decide = async (item: ClassSuggestion, approved: boolean) => {
    try { await api.put(`/applications/${appId}/classes/${item.id}/approve`, { suggestion_id: item.id, approved }); await load(); }
    catch (error) { toast({ title: "Не удалось сохранить выбор", description: messageOf(error, "Попробуйте ещё раз"), variant: "destructive" }); }
  };

  const run = async () => {
    setRunning(true);
    try { await api.post(`/applications/${appId}/full-analysis`); toast({ title: "Проверка завершена", description: "Результат и основные риски готовы." }); onResult(); }
    catch (error) { toast({ title: "Проверка не выполнена", description: messageOf(error, "Попробуйте ещё раз"), variant: "destructive" }); }
    finally { setRunning(false); }
  };

  if (loading) return <div className="flex min-h-48 items-center justify-center text-[#6d6d7d]"><Loader2 className="mr-2 h-5 w-5 animate-spin" /> Проверяем данные…</div>;

  const attention = reconciliation?.items.filter((item) => item.blocks_document_generation || ["missing", "conflict", "needs_review"].includes(item.status)) ?? [];
  const approved = classes.filter((item) => item.approved === true).length;

  return (
    <ClientPanel title="Проверьте данные и классы" description="Перед анализом убедитесь, что сведения верны. Здесь нет технических деталей — только решения, которые влияют на заявку.">
      <div className="grid gap-5 lg:grid-cols-2">
        <section className="rounded-[1.3rem] border border-[#11113f]/10 p-5 sm:p-6">
          <div className="flex items-center justify-between gap-3"><h3 className="text-xl font-semibold">Данные заявления</h3><Badge variant="outline">{attention.length ? `Нужно проверить: ${attention.length}` : "Готово"}</Badge></div>
          <div className="mt-5 space-y-3">
            {attention.length === 0 ? <div className="flex items-start gap-3 rounded-xl bg-emerald-50 p-4 text-emerald-900"><CheckCircle2 className="mt-0.5 h-5 w-5 shrink-0" /><div><p className="font-semibold">Обязательные данные заполнены</p><p className="mt-1 text-sm text-emerald-800">Перейдите к выбору классов и запуску проверки.</p></div></div> : attention.slice(0, 6).map((item) => <div key={item.case_field} className="flex items-start gap-3 rounded-xl bg-amber-50 p-4"><AlertCircle className="mt-0.5 h-5 w-5 shrink-0 text-amber-700" /><div><p className="font-semibold">{item.label}</p><p className="mt-1 text-sm text-amber-900/70">{item.registry_value || item.case_value ? "Проверьте найденное значение" : "Нужно заполнить вручную в разделе «Данные»"}</p></div></div>)}
          </div>
        </section>

        <section className="rounded-[1.3rem] border border-[#11113f]/10 p-5 sm:p-6">
          <div className="flex items-center justify-between gap-3"><h3 className="inline-flex items-center gap-1 text-xl font-semibold">Классы товаров и услуг <HelpTip text="МКТУ — международный справочник из 45 классов. Классы 1–34 относятся к товарам, 35–45 — к услугам. Знак защищается не вообще, а только для выбранных товаров и услуг." /></h3><Badge variant="outline">Выбрано: {approved}</Badge></div>
          <p className="mt-2 text-sm leading-relaxed text-[#6d6d7d]">Система группирует вашу деятельность по международному справочнику МКТУ. Подтвердите только те направления, которыми вы действительно занимаетесь или планируете заниматься.</p>
          <div className="mt-5 space-y-3">
            {classes.length === 0 ? <div className="rounded-xl bg-[#f8f7f4] p-4 text-sm text-[#6d6d7d]">Предложений пока нет. Запустите проверку — система сначала подберёт классы по вашему описанию товаров и услуг.</div> : classes.map((item) => <div key={item.id} className={cn("rounded-xl border p-4", item.approved === true ? "border-emerald-300 bg-emerald-50" : item.approved === false ? "border-[#11113f]/10 bg-[#f8f7f4] opacity-70" : "border-amber-200 bg-amber-50")}><div className="flex items-start justify-between gap-3"><div><p className="font-semibold">Класс {item.class_number}</p><p className="mt-1 text-sm text-[#6d6d7d]">{item.class_description || "Описание класса будет уточнено при анализе"}</p>{item.rationale && <p className="mt-2 rounded-lg bg-white/70 px-3 py-2 text-xs leading-relaxed text-[#55556f]"><span className="font-semibold text-[#11113f]">Почему предложен:</span> {item.rationale}</p>}</div><div className="flex gap-2"><Button size="sm" variant={item.approved === true ? "default" : "outline"} className="rounded-full" onClick={() => void decide(item, true)}><Check className="h-4 w-4" /> Подходит</Button><Button size="sm" variant="ghost" className="rounded-full" onClick={() => void decide(item, false)}>Не подходит</Button></div></div></div>)}
          </div>
        </section>
      </div>
      <div className="mt-7 rounded-[1.2rem] bg-[#11113f] p-5 text-white sm:flex sm:items-center sm:justify-between sm:gap-6"><div><p className="font-semibold">{running ? phases[phase] : "Готовы проверить знак?"}</p><p className="mt-1 text-sm text-white/65">{running ? "Обычно проверка занимает до двух минут. Можно дождаться результата на этом экране." : "Поиск проводится прежде всего в выбранных классах товаров и услуг."}</p>{running && <div className="mt-3 flex gap-1.5">{phases.map((_, index) => <span key={index} className={cn("h-1.5 w-10 rounded-full", index <= phase ? "bg-[#43c7c2]" : "bg-white/15")} />)}</div>}</div><Button disabled={running} onClick={run} className="mt-4 rounded-full bg-[#12aaa5] px-6 hover:bg-[#0d918d] sm:mt-0">{running ? <Loader2 className="h-4 w-4 animate-spin" /> : <Play className="h-4 w-4" />} {running ? "Идёт проверка" : "Запустить проверку"}</Button></div>
    </ClientPanel>
  );
}

function ClientResult({ appId, draftRequest, onEditData }: { appId: number; draftRequest: number; onEditData: () => void }) {
  const { toast } = useToast();
  const [report, setReport] = useState<RiskReport | null>(null);
  const [memo, setMemo] = useState<Recommendation | null>(null);
  const [classes, setClasses] = useState<ClassSuggestion[]>([]);
  const [loading, setLoading] = useState(true);
  const [running, setRunning] = useState(false);

  const load = async () => {
    setLoading(true);
    const [risk, recommendation, classData] = await Promise.all([
      api.get<RiskReport>(`/applications/${appId}/risk-report`).catch(() => null),
      api.get<Recommendation>(`/applications/${appId}/recommendation`).catch(() => null),
      api.get<{ suggestions: ClassSuggestion[] }>(`/applications/${appId}/classes`).catch(() => ({ suggestions: [] })),
    ]);
    setReport(risk); setMemo(recommendation); setClasses(classData.suggestions); setLoading(false);
  };
  useEffect(() => { void load(); }, [appId]);

  const rerun = async () => { setRunning(true); try { await api.post(`/applications/${appId}/full-analysis`); await load(); } catch (error) { toast({ title: "Не удалось обновить результат", description: messageOf(error, "Попробуйте позже"), variant: "destructive" }); } finally { setRunning(false); } };
  const findings = useMemo(() => Object.values(report?.sections || {}).flatMap((section) => section?.findings || []), [report]);
  const risk = report?.overall_risk;
  const incomplete = report?.is_complete === false;
  const presentation = incomplete
    ? { title: "Проверку нужно завершить", tone: "border-amber-200 bg-amber-50", icon: ShieldAlert, color: "text-amber-700" }
    : risk ? {
    low: { title: "Можно продолжать", tone: "border-emerald-200 bg-emerald-50", icon: ShieldCheck, color: "text-emerald-700" },
    medium: { title: "Продолжайте с осторожностью", tone: "border-amber-200 bg-amber-50", icon: ShieldAlert, color: "text-amber-700" },
    high: { title: "Сначала доработайте знак", tone: "border-orange-200 bg-orange-50", icon: ShieldAlert, color: "text-orange-700" },
    critical: { title: "Подача не рекомендуется", tone: "border-red-200 bg-red-50", icon: AlertCircle, color: "text-red-700" },
  }[risk] : null;

  if (loading) return <div className="flex min-h-48 items-center justify-center text-[#6d6d7d]"><Loader2 className="mr-2 h-5 w-5 animate-spin" /> Загружаем результат…</div>;

  if (!presentation) return <ClientPanel title="Результата пока нет" description="Запустите проверку на предыдущем шаге. Система подберёт классы, найдёт сходные товарные знаки и подготовит понятную рекомендацию."><Button onClick={rerun} disabled={running} className="rounded-full bg-[#0d9f9b] px-6 hover:bg-[#078984]">{running ? <Loader2 className="h-4 w-4 animate-spin" /> : <Play className="h-4 w-4" />} Запустить проверку</Button></ClientPanel>;

  const ResultIcon = presentation.icon;
  const adverseFindings = findings.filter((item) =>
    ["medium", "high", "critical"].includes(item.level || ""),
  );
  const sectionReasons = Object.values(report?.sections || {})
    .filter((item) => item?.is_inconclusive)
    .map((item) => item?.inconclusive_reason)
    .filter((item): item is string => Boolean(item));
  const incompleteReasons = report?.incomplete_checks?.length
    ? report.incomplete_checks
    : sectionReasons;
  const visibleRisks = adverseFindings.length > 0
    ? adverseFindings.slice(0, 5).map((item) => item.description)
    : !incomplete && risk && risk !== "low"
      ? (memo?.key_risks_json || []).slice(0, 5)
      : [];
  return (
    <ClientPanel title="Результат проверки" description="Главный вывод, выбранные классы и риски, которые важно учесть до подачи.">
      <section className={cn("rounded-[1.5rem] border p-6 sm:p-8", presentation.tone)}>
        <div className="flex flex-col gap-5 sm:flex-row sm:items-start sm:justify-between"><div className="flex items-start gap-4"><span className="flex h-12 w-12 shrink-0 items-center justify-center rounded-full bg-white"><ResultIcon className={cn("h-6 w-6", presentation.color)} /></span><div><p className="inline-flex items-center gap-1 text-xs font-bold uppercase tracking-[0.15em] text-[#6d6d7d]">Предварительный вывод <HelpTip text="Это автоматическая предварительная оценка по введённым данным и доступному поиску. Окончательное решение о регистрации принимает Роспатент." /></p><h3 className={cn("mt-1 text-3xl font-semibold", presentation.color)}>{presentation.title}</h3><p className="mt-3 max-w-3xl leading-relaxed text-[#11113f]">{memo?.summary || memo?.risk_assessment || "Проверка завершена. Изучите отмеченные риски перед подачей."}</p></div></div><Button variant="outline" className="rounded-full bg-white" disabled={running} onClick={rerun}>{running && <Loader2 className="h-4 w-4 animate-spin" />} Обновить</Button></div>
      </section>
      <div className="mt-6 grid gap-5 lg:grid-cols-2">
        <section className="rounded-[1.3rem] border border-[#11113f]/10 p-5 sm:p-6"><h3 className="text-xl font-semibold">Что делать дальше</h3><p className="mt-3 leading-relaxed text-[#55556f]">{memo?.recommended_action ? ACTION_LABELS[memo.recommended_action] ?? "Проверьте результат перед подачей" : incomplete ? "Дождитесь завершения всех проверок и повторите анализ." : "Проверьте выбранные классы и переходите к подготовке заявления."}</p><div className="mt-5 flex flex-wrap gap-2">{classes.filter((item) => item.approved !== false).map((item) => <Badge key={item.id} className="bg-[#e8f7f6] text-[#087c78] hover:bg-[#e8f7f6]">МКТУ {item.class_number}</Badge>)}</div></section>
        <section className="rounded-[1.3rem] border border-[#11113f]/10 p-5 sm:p-6">
          <h3 className="text-xl font-semibold">{incomplete ? "Что осталось проверить" : visibleRisks.length ? "Риски для регистрации" : "Результат проверки"}</h3>
          <div className="mt-4 space-y-3">
            {(incomplete ? incompleteReasons : visibleRisks).map((item, index) => <div key={index} className="flex items-start gap-3 text-sm leading-relaxed text-[#55556f]"><span className={cn("mt-2 h-2 w-2 shrink-0 rounded-full", incomplete ? "bg-amber-500" : "bg-[#ef5b62]")} />{item}</div>)}
            {incomplete && incompleteReasons.length === 0 && <p className="text-sm text-[#6d6d7d]">Одна или несколько частей анализа не дали надёжного результата. Повторите проверку позже.</p>}
            {!incomplete && visibleRisks.length === 0 && <div className="flex items-start gap-3 rounded-xl bg-emerald-50 p-4 text-emerald-900"><CheckCircle2 className="mt-0.5 h-5 w-5 shrink-0" /><p className="text-sm leading-relaxed">Существенные препятствия не выявлены. Положительные результаты отдельных проверок не считаются рисками и здесь не перечисляются.</p></div>}
          </div>
        </section>
      </div>
      <ClientDraftPreview appId={appId} analysisComplete={!incomplete} openRequest={draftRequest} onEditData={onEditData} />
      <ClientFeeEstimate appId={appId} />
      <p className="mt-6 text-sm leading-relaxed text-[#6d6d7d]">Результат сформирован автоматически на основе введённых данных, выбранных классов и доступных реестров. Он помогает принять решение, но не является гарантией регистрации или юридической консультацией.</p>
    </ClientPanel>
  );
}

interface DraftField {
  label: string;
  value: string | null;
  fill: string;
  required: boolean;
  needs_attention: boolean;
  origin: string | null;
}

interface DraftForm {
  title: string;
  sections: Array<{ id: string; title: string; fields: DraftField[] }>;
  required_count: number;
  required_done: number;
  blocking: string[];
  can_generate: boolean;
}

function ClientDraftPreview({ appId, analysisComplete, openRequest, onEditData }: { appId: number; analysisComplete: boolean; openRequest: number; onEditData: () => void }) {
  const draft = useApi<DraftForm>(`/applications/${appId}/draft-form`);
  const [open, setOpen] = useState(openRequest > 0);
  const [downloading, setDownloading] = useState(false);
  const { toast } = useToast();

  const download = async () => {
    setDownloading(true);
    try {
      await api.download(`/applications/${appId}/draft-preview/download`, `chernovik-zayavleniya-${appId}.docx`);
      toast({ title: "Черновик скачан", description: "Это рабочий DOCX: проверьте и дополните его перед подачей." });
    } catch (error) {
      toast({ title: "Не удалось скачать черновик", description: messageOf(error, "Попробуйте ещё раз"), variant: "destructive" });
    } finally { setDownloading(false); }
  };

  useEffect(() => {
    if (!openRequest) return;
    setOpen(true);
    window.setTimeout(() => document.getElementById("client-draft")?.scrollIntoView({ behavior: "smooth", block: "start" }), 0);
  }, [openRequest]);

  return (
    <section id="client-draft" className="mt-6 scroll-mt-6 overflow-hidden rounded-[1.4rem] border-2 border-[#0d9f9b]/35 bg-[#f0f8f7]">
      <div className="flex flex-col gap-5 p-6 sm:flex-row sm:items-center sm:justify-between">
        <div className="flex items-start gap-4">
          <span className="flex h-12 w-12 shrink-0 items-center justify-center rounded-full bg-white text-[#087c78]"><FileSignature className="h-6 w-6" /></span>
          <div>
            <p className="text-xs font-bold uppercase tracking-[0.14em] text-[#087c78]">Следующий шаг</p>
            <h3 className="mt-1 text-2xl font-semibold text-[#11113f]">Черновик заявления в Роспатент</h3>
            <p className="mt-2 max-w-2xl text-sm leading-relaxed text-[#55556f]">
              Здесь видно, какие сведения уже попадут в заявление и какие поля ещё нужно заполнить до формирования файла.
            </p>
          </div>
        </div>
        <div className="flex shrink-0 flex-wrap gap-2">
          <Button variant="outline" className="rounded-full border-[#0d9f9b]/40 bg-white" onClick={() => setOpen((value) => !value)} disabled={draft.isLoading}>
            {draft.isLoading ? <Loader2 className="h-4 w-4 animate-spin" /> : <FileText className="h-4 w-4" />}
            {open ? "Скрыть черновик" : "Открыть черновик"}
          </Button>
          <Button className="rounded-full bg-[#0d9f9b] hover:bg-[#078984]" onClick={() => void download()} disabled={downloading}>
            {downloading ? <Loader2 className="h-4 w-4 animate-spin" /> : <Download className="h-4 w-4" />} Скачать DOCX
          </Button>
        </div>
      </div>

      {open && draft.data && (
        <div className="border-t border-[#0d9f9b]/20 bg-white p-5 sm:p-6">
          <div className="mb-5 flex flex-col gap-3 rounded-xl bg-[#f8f7f4] p-4 sm:flex-row sm:items-center sm:justify-between">
            <div>
              <p className="font-semibold text-[#11113f]">Обязательных полей заполнено: {draft.data.required_done} из {draft.data.required_count}</p>
              <p className="mt-1 text-sm text-[#6d6d7d]">{draft.data.can_generate ? "Данных достаточно для формирования чернового файла." : `Нужно дополнить: ${draft.data.blocking.join(", ") || "обязательные сведения"}.`}</p>
            </div>
            {!draft.data.can_generate && <Button variant="outline" className="rounded-full bg-white" onClick={onEditData}><PencilLine className="h-4 w-4" /> Дополнить данные</Button>}
          </div>

          <div className="space-y-5">
            {draft.data.sections.map((section) => {
              const fields = section.fields.filter((field) => field.value || field.required);
              if (!fields.length) return null;
              return <div key={section.id}><h4 className="mb-3 font-semibold text-[#11113f]">{section.title}</h4><div className="grid gap-3 sm:grid-cols-2">{fields.map((field, index) => <div key={`${section.id}-${index}`} className={cn("rounded-xl border p-4", field.needs_attention ? "border-amber-300 bg-amber-50" : "border-[#11113f]/10 bg-white")}><div className="flex items-start justify-between gap-2"><p className="text-sm font-semibold text-[#11113f]">{field.label}</p>{field.needs_attention ? <span className="rounded-full bg-amber-100 px-2 py-1 text-[10px] font-bold text-amber-800">Нужно заполнить</span> : <CheckCircle2 className="h-4 w-4 shrink-0 text-emerald-600" />}</div><p className="mt-2 text-sm leading-relaxed text-[#55556f]">{field.value || "Пока не заполнено"}</p>{field.value && <p className="mt-2 text-[11px] text-[#77778a]">{field.origin ? `Источник: ${field.origin}` : "Взято из данных заявки"}</p>}</div>)}</div></div>;
            })}
          </div>

          {!analysisComplete && <div className="mt-5 flex items-start gap-3 rounded-xl border border-amber-200 bg-amber-50 p-4 text-sm text-amber-900"><LockKeyhole className="mt-0.5 h-5 w-5 shrink-0" /><p><span className="font-semibold">Финальный файл пока не формируется.</span> Сначала завершите проверку и подтвердите классы товаров и услуг. Сам черновик уже доступен для просмотра и дополнения.</p></div>}
        </div>
      )}
      {open && draft.error && <div className="border-t border-red-200 bg-red-50 p-5 text-sm text-red-800">Не удалось загрузить черновик: {draft.error} <Button variant="ghost" size="sm" onClick={draft.reload}>Повторить</Button></div>}
    </section>
  );
}

interface FeeEstimate {
  can_calculate: boolean;
  class_count: number;
  class_basis: "confirmed" | "suggested" | "none";
  payments: Array<{ code: string; title: string; amount: number; when: string }>;
  filing_total: number | null;
  registration_total: number | null;
  total_electronic: number | null;
  paper_certificate_extra: number;
  calculated_at: string;
  source_url: string;
  warnings: string[];
}

const rubles = (value: number | null) => value == null ? "—" : `${new Intl.NumberFormat("ru-RU").format(value)} ₽`;

function ClientFeeEstimate({ appId }: { appId: number }) {
  const fees = useApi<FeeEstimate>(`/applications/${appId}/fees`);
  return (
    <section className="mt-6 overflow-hidden rounded-[1.4rem] border border-[#11113f]/10 bg-white">
      <div className="flex items-start gap-4 p-6">
        <span className="flex h-12 w-12 shrink-0 items-center justify-center rounded-full bg-[#e8f7f6] text-[#087c78]"><ReceiptText className="h-6 w-6" /></span>
        <div><p className="text-xs font-bold uppercase tracking-[0.14em] text-[#087c78]">Стоимость подачи</p><h3 className="mt-1 text-2xl font-semibold text-[#11113f]">Расчёт пошлин Роспатента</h3><p className="mt-2 text-sm leading-relaxed text-[#55556f]">Сумма рассчитана по выбранным классам. Платежи вносятся в два этапа.</p></div>
      </div>
      {fees.isLoading && <div className="border-t p-6 text-sm text-[#6d6d7d]"><Loader2 className="mr-2 inline h-4 w-4 animate-spin" /> Рассчитываем…</div>}
      {fees.data && !fees.data.can_calculate && <div className="border-t border-amber-200 bg-amber-50 p-5 text-sm text-amber-900">Сначала подтвердите хотя бы один класс товаров или услуг.</div>}
      {fees.data?.can_calculate && <div className="border-t border-[#11113f]/10 p-5 sm:p-6">
        <div className="grid gap-4 sm:grid-cols-3">
          <div className="rounded-xl bg-[#f8f7f4] p-4"><p className="text-xs text-[#6d6d7d]">При подаче заявки</p><p className="mt-1 text-2xl font-semibold text-[#11113f]">{rubles(fees.data.filing_total)}</p></div>
          <div className="rounded-xl bg-[#f8f7f4] p-4"><p className="text-xs text-[#6d6d7d]">После положительного решения</p><p className="mt-1 text-2xl font-semibold text-[#11113f]">{rubles(fees.data.registration_total)}</p></div>
          <div className="rounded-xl bg-[#11113f] p-4 text-white"><p className="text-xs text-white/65">Всего, электронное свидетельство</p><p className="mt-1 text-2xl font-semibold">{rubles(fees.data.total_electronic)}</p></div>
        </div>
        <div className="mt-5 space-y-2">{fees.data.payments.map((payment) => <div key={payment.code} className="flex flex-col justify-between gap-1 border-b border-[#11113f]/8 py-3 text-sm sm:flex-row sm:items-center"><div><span className="font-semibold">{payment.title}</span><span className="ml-2 text-xs text-[#77778a]">п. {payment.code}</span><p className="mt-1 text-xs text-[#77778a]">{payment.when}</p></div><span className="font-semibold text-[#11113f]">{rubles(payment.amount)}</span></div>)}</div>
        <p className="mt-4 text-sm text-[#55556f]">Расчёт для {fees.data.class_count} кл. МКТУ. Бумажное свидетельство по желанию: +{rubles(fees.data.paper_certificate_extra)}.</p>
        <div className="mt-4 rounded-xl bg-amber-50 p-4 text-xs leading-relaxed text-amber-900">{fees.data.warnings.map((warning) => <p key={warning}>• {warning}</p>)}</div>
        <a href={fees.data.source_url} target="_blank" rel="noreferrer" className="mt-4 inline-block text-xs font-semibold text-[#087c78] underline underline-offset-4">Официальная таблица пошлин Роспатента ↗</a>
      </div>}
      {fees.error && <div className="border-t border-red-200 bg-red-50 p-5 text-sm text-red-800">Не удалось рассчитать пошлины: {fees.error}</div>}
    </section>
  );
}
