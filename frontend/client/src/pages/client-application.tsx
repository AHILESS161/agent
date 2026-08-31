import { useEffect, useMemo, useRef, useState } from "react";
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
  Archive,
  BookOpenCheck,
  RefreshCw,
  ImageIcon,
  Upload,
  Trash2,
  MessageSquareText,
} from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import { Checkbox } from "@/components/ui/checkbox";
import { Badge } from "@/components/ui/badge";
import { useToast } from "@/hooks/use-toast";
import { api, ApiError, DOCUMENT_KIND_LABELS, type SourceDocumentDto } from "@/lib/api";
import { useCase } from "@/lib/use-cases";
import { cn } from "@/lib/utils";
import { HelpTip } from "@/components/help-tip";
import { useApi } from "@/lib/use-api";
import { useAuth } from "@/lib/auth";
import { COUNTRY_OPTIONS } from "@/lib/country-codes";
import { MARK_TYPE_LABELS, type Application, type Client, type MarkType } from "@shared/schema";
import { OfficeActionResponse } from "@/components/office-action-response";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";

type Section = "upload" | "review" | "analysis" | "fees" | "documents" | "response";

interface ClassSuggestion {
  id: number;
  class_number: number;
  class_description: string | null;
  rationale: string | null;
  approved: boolean | null;
}

interface ClassNarrowingPreview {
  suggestion_id: number;
  class_number: number;
  source_count: number;
  selected_count: number;
  selected_items: string[];
  proposed_description: string;
  rationale: string;
  assumptions: string[];
}

interface RiskFindingSummary {
  id: number;
  category?: string;
  explanation: string;
  recommendation?: string;
  recommended_action?: string | null;
  level?: string;
  legal_basis?: string;
  verification?: {
    registry_record?: {
      mark_text?: string;
      classes?: Array<number | string>;
      owner?: string;
      status?: string;
      source?: string;
      application_number?: string;
      registration_number?: string;
    };
    image_comparison?: { score: number } | null;
    similarity?: { phonetic?: number; visual?: number; semantic?: number; goods?: number; image_visual?: number | null };
    search_scope?: string;
  };
}

interface RiskSection {
  summary?: string | null;
  findings?: RiskFindingSummary[];
  is_inconclusive?: boolean;
  inconclusive_reason?: string | null;
  missing_data?: string[];
  limitations?: string[];
  provenance?: {
    verification?: {
      records_examined?: number;
      search_errors?: string[];
      skipped?: boolean;
      blocked_by?: string;
      skip_reason?: string;
      blocking_risk?: string | null;
      search_complete?: boolean;
    };
  };
}

interface RiskReport {
  overall_risk: "low" | "medium" | "high" | "critical" | null;
  is_complete: boolean;
  incomplete_checks?: string[];
  sections: Record<string, RiskSection | null>;
  last_completed_sections?: Record<string, RiskSection | null>;
  latest_attempts?: Record<string, RiskSection | null>;
  refresh_warnings?: Record<string, string>;
}

interface Recommendation {
  summary: string | null;
  risk_assessment: string | null;
  recommended_action: string | null;
  key_risks_json: string[] | null;
}

interface AnalysisJob {
  id: number;
  application_id: number;
  status: "queued" | "running" | "retrying" | "completed" | "failed" | "cancelled";
  progress: number;
  current_step: string;
  message: string;
  retry_count: number;
  max_retries: number;
  error_message?: string | null;
}

interface MarkImageDto {
  document_id: number;
  filename: string;
  file_size: number;
  mime_type: string;
  width: number;
  height: number;
  format: string;
  dominant_colors: string[];
  recognized_text: string;
  ocr_confidence: number | null;
  ocr_warning: string | null;
  visual_search_supported: boolean;
  visual_search_notice: string;
}

interface MarkDescriptionDto {
  description: string;
  colors: string[];
  transliteration: string;
  translation: string;
  model: string;
  requires_confirmation: boolean;
}

type FieldSourceKind = "document" | "system" | "user" | "rospatent" | "profile";

interface FieldSourceDto {
  code: string;
  source: FieldSourceKind;
  label: string;
  detail: string;
  filled: boolean;
  verification_required: boolean;
}

interface RegistrantPrefillDto {
  document_kind: string | null;
  client_type: "company" | "sole_proprietor" | "individual" | null;
  prefill: {
    name?: string;
    short_name?: string;
    inn?: string;
    ogrn?: string;
    kpp?: string;
    address?: string;
    business_activity?: string;
    signatory_last_name?: string;
    signatory_first_name?: string;
    signatory_middle_name?: string;
    signatory_position?: string;
  };
  warning: string | null;
}

interface ExtractedRegistrantFieldDto {
  field_path: string;
  raw_value: string | null;
  normalized_value: string | null;
  validation_error: string | null;
}

interface RepresentativeDto {
  id: number;
  client_id: number;
  full_name: string;
  email: string | null;
  phone: string | null;
  address: string | null;
  role: string | null;
  is_patent_attorney: boolean;
  patent_attorney_registration_number: string | null;
  authority_type: "power_of_attorney" | "law" | "charter";
  poa_reference: string | null;
}

const SECTION_META: Array<{ id: Section; label: string; icon: typeof Circle }> = [
  { id: "upload", label: "Загрузка", icon: Upload },
  { id: "review", label: "Проверка данных", icon: PencilLine },
  { id: "analysis", label: "Анализ", icon: Sparkles },
  { id: "fees", label: "Пошлины", icon: ReceiptText },
  { id: "documents", label: "Документы", icon: Archive },
  { id: "response", label: "Ответ Роспатенту", icon: MessageSquareText },
];

const sectionFromLocation = (location: string): Section | null => {
  const query = location.split("?", 2)[1] || "";
  const value = new URLSearchParams(query).get("step");
  return SECTION_META.some((item) => item.id === value) ? value as Section : null;
};

function messageOf(error: unknown, fallback: string) {
  return error instanceof ApiError ? error.message : fallback;
}

function transliterateRussian(value: string) {
  const letters: Record<string, string> = {
    а: "a", б: "b", в: "v", г: "g", д: "d", е: "e", ё: "yo", ж: "zh",
    з: "z", и: "i", й: "y", к: "k", л: "l", м: "m", н: "n", о: "o",
    п: "p", р: "r", с: "s", т: "t", у: "u", ф: "f", х: "kh", ц: "ts",
    ч: "ch", ш: "sh", щ: "shch", ъ: "", ы: "y", ь: "", э: "e", ю: "yu", я: "ya",
  };
  if (!/[А-ЯЁ]/i.test(value)) return "";
  return Array.from(value.toLocaleLowerCase("ru-RU"))
    .map((letter) => letters[letter] ?? letter)
    .join("")
    .replace(/\s+/g, " ")
    .trim()
    .toLocaleUpperCase("ru-RU");
}

export default function ClientApplicationPage() {
  const params = useParams<{ id: string }>();
  const appId = Number(params.id);
  const [, setLocation] = useLocation();
  const current = useCase(appId);
  const [section, setSection] = useState<Section>(() => sectionFromLocation(window.location.href) || "upload");
  const [transitionDirection, setTransitionDirection] = useState<"forward" | "backward">("forward");
  const [analysisPending, setAnalysisPending] = useState(false);
  const stageRef = useRef<HTMLDivElement>(null);
  const firstSectionRender = useRef(true);

  const goToSection = (next: Section) => {
    if (next === section) return;
    const currentIndex = SECTION_META.findIndex((item) => item.id === section);
    const nextIndex = SECTION_META.findIndex((item) => item.id === next);
    setTransitionDirection(nextIndex >= currentIndex ? "forward" : "backward");
    setSection(next);
    setLocation(`/applications/${appId}?step=${next}`);
  };

  useEffect(() => {
    const restoreFromBrowserHistory = () => {
      const requested = sectionFromLocation(window.location.href);
      if (!requested) return;
      setSection((currentSection) => {
        if (requested === currentSection) return currentSection;
        const currentIndex = SECTION_META.findIndex((item) => item.id === currentSection);
        const nextIndex = SECTION_META.findIndex((item) => item.id === requested);
        setTransitionDirection(nextIndex >= currentIndex ? "forward" : "backward");
        return requested;
      });
    };
    window.addEventListener("popstate", restoreFromBrowserHistory);
    return () => window.removeEventListener("popstate", restoreFromBrowserHistory);
  }, []);

  useEffect(() => {
    if (firstSectionRender.current) {
      firstSectionRender.current = false;
      return;
    }
    const reducedMotion = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
    stageRef.current?.scrollIntoView({ behavior: reducedMotion ? "auto" : "smooth", block: "start" });
  }, [section]);

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
    <div className="min-w-0 space-y-7">
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
            <button type="button" onClick={() => goToSection("documents")} className="text-sm font-semibold text-[#43c7c2] underline decoration-[#43c7c2]/40 underline-offset-4 transition-colors hover:text-white">
              Готовые документы и памятка →
            </button>
          </div>
        </div>
      </section>

      <nav className="grid grid-cols-2 gap-2 rounded-[1.3rem] border border-[#11113f]/10 bg-white p-2 lg:grid-cols-6">
        {SECTION_META.map((item, index) => {
          const active = section === item.id;
          return (
            <button
              key={item.id}
              type="button"
              onClick={() => goToSection(item.id)}
              className={cn(
                "flex min-h-14 items-center gap-3 rounded-xl px-3 text-left text-sm font-semibold transition-[background-color,color,transform,box-shadow] duration-300 ease-out active:scale-[0.98]",
                active ? "bg-[#e9f7f6] text-[#087c78] shadow-[inset_0_0_0_1px_rgba(13,159,155,0.12)]" : "text-[#66667a] hover:bg-[#f6f5f1] hover:text-[#11113f]",
              )}
            >
              <span className={cn("flex h-8 w-8 shrink-0 items-center justify-center rounded-full border text-xs transition-[background-color,border-color,color,transform] duration-300", active ? "client-step-active border-[#0d9f9b] bg-[#0d9f9b] text-white" : "border-[#11113f]/15")}>{index + 1}</span>
              {item.label}
            </button>
          );
        })}
      </nav>

      <div ref={stageRef} className="min-w-0 scroll-mt-5 overflow-hidden rounded-[1.8rem] border border-[#11113f]/10 bg-white p-5 shadow-[0_14px_45px_rgba(21,21,55,0.05)] sm:p-8 lg:p-10">
        <div key={section} className={cn("client-stage-enter", transitionDirection === "backward" && "client-stage-enter-backward")}>
          {section === "upload" && <ClientDataForm mode="upload" application={application} client={client} onSaved={current.reload} onNext={() => goToSection("review")} />}
          {section === "review" && <ClientDataForm mode="review" application={application} client={client} appId={appId} onSaved={current.reload} onAnalysis={() => { setAnalysisPending(true); goToSection("analysis"); }} />}
          {section === "analysis" && <ClientResult application={application} appId={appId} analysisPending={analysisPending} onAnalysisComplete={() => setAnalysisPending(false)} onReview={() => goToSection("review")} onApplication={() => goToSection("fees")} onEditData={() => goToSection("review")} />}
          {section === "fees" && <ClientFeeEstimate appId={appId} onDocuments={() => goToSection("documents")} onReview={() => goToSection("review")} />}
          {section === "documents" && <ClientFilingPackage appId={appId} application={application} client={client} onSaved={current.reload} onGoToSection={goToSection} />}
          {section === "response" && <OfficeActionResponse appId={appId} />}
        </div>
      </div>
    </div>
  );
}

function ClientPanel({ title, description, children }: { title: string; description: string; children: React.ReactNode }) {
  return (
    <div className="min-w-0">
      <p className="text-sm font-bold uppercase tracking-[0.14em] text-[#0d9f9b]">Товарный знак</p>
      <h2 className="mt-2 text-3xl font-semibold text-[#11113f]">{title}</h2>
      <p className="mt-3 max-w-3xl leading-relaxed text-[#6d6d7d]">{description}</p>
      <div className="mt-8 min-w-0">{children}</div>
    </div>
  );
}

function ClientDataForm({ mode, application, client, appId, onSaved, onNext, onAnalysis }: { mode: "upload" | "review"; application: any; client: any; appId?: number; onSaved: () => void | Promise<void>; onNext?: () => void; onAnalysis?: () => void }) {
  const { toast } = useToast();
  const { user, refreshProfile } = useAuth();
  const filingRules = useApi<FilingPackageStatus>(
    mode === "review" ? `/applications/${application.id}/filing-package` : null,
  );
  const applicantDocumentInput = useRef<HTMLInputElement>(null);
  const powerOfAttorneyInput = useRef<HTMLInputElement>(null);
  const [saving, setSaving] = useState(false);
  const [savingProfile, setSavingProfile] = useState(false);
  const [autosaveStatus, setAutosaveStatus] = useState<"idle" | "dirty" | "saving" | "saved" | "error">("idle");
  const [dataConfirmed, setDataConfirmed] = useState(false);
  const [confirmingData, setConfirmingData] = useState(false);
  const autosaveTimer = useRef<number | null>(null);
  const autosaveReady = useRef(false);
  const lastSavedSnapshot = useRef("");
  const [autoFilling, setAutoFilling] = useState(false);
  const [applicantDocumentUploading, setApplicantDocumentUploading] = useState(false);
  const [powerOfAttorneyUploading, setPowerOfAttorneyUploading] = useState(false);
  const [applicantDocuments, setApplicantDocuments] = useState<SourceDocumentDto[]>([]);
  const [imageUploading, setImageUploading] = useState(false);
  const [audioUploading, setAudioUploading] = useState(false);
  const [markAudio, setMarkAudio] = useState<SourceDocumentDto | null>(null);
  const [markImage, setMarkImage] = useState<MarkImageDto | null>(null);
  const [previewUrl, setPreviewUrl] = useState<string | null>(null);
  const automaticDescriptionRequested = useRef(false);
  const [form, setForm] = useState({
    name: client?.fullNameOrCompanyName || "",
    inn: client?.inn || "",
    ogrn: client?.ogrnOrOgrnip || "",
    kpp: client?.kpp || "",
    address: client?.address || "",
    country: client?.countryCode || "RU",
    email: client?.email || "",
    phone: client?.phone || "",
    markName: application.markName || "",
    markText: application.markText || application.markName || "",
    markType: application.markType as MarkType,
    business: application.businessDescription || "",
    goods: application.goodsServicesRaw || "",
    description: application.descriptionOfMark || "",
    colors: application.colorsClaimed || "",
    transliteration: application.transliteration || "",
    translation: application.translation || "",
    filingMethod: application.filingMethod || "electronic",
    requestPaperCertificate: application.requestPaperCertificate || false,
    signatoryName: application.signatoryName
      || (client?.type === "company" ? "" : client?.fullNameOrCompanyName || ""),
    signatoryPosition: application.signatoryPosition || "",
    signatureDate: application.signatureDate || new Date().toISOString().slice(0, 10),
  });
  const [usesRepresentative, setUsesRepresentative] = useState(Boolean(application.representativeId));
  const [representative, setRepresentative] = useState({
    id: application.representativeId as number | null,
    fullName: "",
    email: "",
    phone: "",
    address: "",
    role: "",
    isPatentAttorney: false,
    registrationNumber: "",
    authorityType: "power_of_attorney" as "power_of_attorney" | "law" | "charter",
    poaReference: "",
  });

  const set = (key: keyof typeof form, value: string) => setForm((old) => ({ ...old, [key]: value }));
  const activityDescription = form.goods || form.business;
  const imageMark = form.markType === "figurative" || form.markType === "combined";
  const soundMark = form.markType === "sound";
  const powerOfAttorneyDocument = applicantDocuments.find(
    (item) => item.document_kind === "power_of_attorney" && !item.kind_requires_confirmation,
  );
  const foreignWording = /[A-Za-z]/.test(form.markText || form.markName);
  const isApplicable = (code: string, fallback: boolean) => {
    const rule = filingRules.data?.requirements?.requirements.find((item) => item.code === code);
    return rule ? rule.applicable : fallback;
  };
  const sourceFor = (code: string, filled: boolean): FieldSourceDto => (
    filingRules.data?.field_sources?.fields.find((item) => item.code === code)
    || {
      code,
      source: "user",
      label: filled ? "Введено вами" : "Заполнить вручную",
      detail: filled
        ? "Значение сохранено после ввода или изменения пользователем."
        : "Этого значения нет в документах — укажите его самостоятельно.",
      filled,
      verification_required: false,
    }
  );
  const applicantType = filingRules.data?.requirements?.applicant_type || client?.type;
  const normalized = (value?: string | null) => (value || "").trim();
  const profileMatchesForm = Boolean(
    user?.applicantProfile
      && user.applicantProfile.type === applicantType
      && normalized(user.applicantProfile.fullNameOrCompanyName) === normalized(form.name)
      && normalized(user.applicantProfile.inn) === normalized(form.inn)
      && normalized(user.applicantProfile.ogrnOrOgrnip) === normalized(form.ogrn)
      && normalized(user.applicantProfile.kpp) === normalized(form.kpp)
      && normalized(user.applicantProfile.address) === normalized(form.address)
      && normalized(user.applicantProfile.country || "RU") === normalized(form.country || "RU")
      && normalized(user.applicantProfile.email) === normalized(form.email)
      && normalized(user.applicantProfile.phone) === normalized(form.phone),
  );
  const hasGenericImageDescription = (value: string) => {
    const normalized = value.toLocaleLowerCase("ru-RU");
    return !normalized.trim()
      || normalized.includes("графические элементы, приведённые")
      || normalized.includes("графическое исполнение и взаимное расположение элементов приведены")
      || normalized.includes("внешний вид и расположение элементов которой приведены");
  };

  const loadApplicantDocuments = async () => {
    const result = await api.get<{ items: SourceDocumentDto[] }>(
      `/applications/${application.id}/source-documents`,
    );
    setApplicantDocuments(
      result.items.filter(
        (item) => !["mark_audio", "mark_image"].includes(item.document_kind),
      ),
    );
    setMarkAudio(
      result.items.filter((item) => item.document_kind === "mark_audio").at(-1) || null,
    );

    // Старые заявки могли сохранить саму выписку и извлечённые поля, но не
    // успеть перенести их в карточку до перехода между экранами. Восстанавливаем
    // такие значения из последней выписки, чтобы не просить загрузить файл ещё
    // раз. Окончательное сохранение происходит после проверки пользователем.
    const registryDocument = result.items.find((item) =>
      ["egrul_extract", "egrip_extract", "unknown_registry_extract"].includes(item.document_kind),
    );
    if (!registryDocument) return;

    let extracted = await api.get<{ items: ExtractedRegistrantFieldDto[] }>(
      `/source-documents/${registryDocument.id}/fields`,
    ).catch(() => ({ items: [] }));
    if (extracted.items.length === 0 && registryDocument.processing_status === "extracted") {
      await api.post(`/source-documents/${registryDocument.id}/extract`).catch(() => undefined);
      extracted = await api.get<{ items: ExtractedRegistrantFieldDto[] }>(
        `/source-documents/${registryDocument.id}/fields`,
      ).catch(() => ({ items: [] }));
    }

    const values = new Map(
      extracted.items
        .filter((item) => !item.validation_error && (item.normalized_value || item.raw_value))
        .map((item) => [item.field_path, (item.normalized_value || item.raw_value || "").trim()]),
    );
    const from = (...paths: string[]) => paths.map((path) => values.get(path)).find(Boolean) || "";
    const restoredSignatory = [
      from("registry.legal_entity.director.last_name", "registry.sole_proprietor.last_name"),
      from("registry.legal_entity.director.first_name", "registry.sole_proprietor.first_name"),
      from("registry.legal_entity.director.middle_name", "registry.sole_proprietor.middle_name"),
    ].filter(Boolean).join(" ");

    setForm((current) => ({
      ...current,
      name: current.name || from("registry.legal_entity.full_name", "registry.sole_proprietor.full_name"),
      inn: current.inn || from("registry.legal_entity.inn", "registry.sole_proprietor.inn"),
      ogrn: current.ogrn || from("registry.legal_entity.ogrn", "registry.sole_proprietor.ogrnip"),
      kpp: current.kpp || from("registry.legal_entity.kpp"),
      address: current.address || from("registry.legal_entity.address.full"),
      business: current.business || from("registry.sole_proprietor.main_activity"),
      signatoryName: current.signatoryName || restoredSignatory,
      signatoryPosition: current.signatoryPosition || from("registry.legal_entity.director.position"),
    }));
  };

  const loadRepresentative = async () => {
    if (!client || mode !== "review") return;
    const items = await api.get<RepresentativeDto[]>(`/clients/${client.id}/representatives`);
    const selected = items.find((item) => item.id === application.representativeId);
    if (!selected) return;
    setUsesRepresentative(true);
    setRepresentative({
      id: selected.id,
      fullName: selected.full_name,
      email: selected.email || "",
      phone: selected.phone || "",
      address: selected.address || "",
      role: selected.role || "",
      isPatentAttorney: selected.is_patent_attorney,
      registrationNumber: selected.patent_attorney_registration_number || "",
      authorityType: selected.authority_type || "power_of_attorney",
      poaReference: selected.poa_reference || "",
    });
  };

  const uploadPowerOfAttorney = async (file?: File) => {
    if (!file) return;
    setPowerOfAttorneyUploading(true);
    try {
      const document = await api.upload<SourceDocumentDto>(
        `/applications/${application.id}/source-documents`,
        file,
      );
      if (document.document_kind !== "power_of_attorney" || document.kind_requires_confirmation) {
        await api.put(`/source-documents/${document.id}/kind`, {
          document_kind: "power_of_attorney",
        });
      }
      await loadApplicantDocuments();
      filingRules.reload();
      toast({ title: "Доверенность добавлена", description: "Файл войдёт в пакет документов для подачи." });
    } catch (error) {
      toast({
        title: "Не удалось загрузить доверенность",
        description: messageOf(error, "Проверьте файл и попробуйте ещё раз"),
        variant: "destructive",
      });
    } finally {
      setPowerOfAttorneyUploading(false);
      if (powerOfAttorneyInput.current) powerOfAttorneyInput.current.value = "";
    }
  };

  const uploadApplicantDocument = async (file?: File) => {
    if (!file) return;
    setApplicantDocumentUploading(true);
    try {
      // Сначала читаем документ для немедленного автозаполнения формы. Затем
      // сохраняем тот же оригинал в заявке: пользователь видит результат до
      // перехода к проверке, а юрист впоследствии видит источник сведений.
      const document = await api.upload<SourceDocumentDto>(
        `/applications/${application.id}/source-documents`,
        file,
      );
      const prefill: RegistrantPrefillDto = await api.upload<RegistrantPrefillDto>(
        "/intake/prefill-registrant",
        file,
      ).catch((): RegistrantPrefillDto => ({
        document_kind: document.document_kind || null,
        client_type: null,
        prefill: {},
        warning: document.warning || "Документ сохранён, но реквизиты не удалось распознать автоматически.",
      }));

      if (document.kind_requires_confirmation && prefill.document_kind) {
        await api.put(`/source-documents/${document.id}/kind`, {
          document_kind: prefill.document_kind,
        }).catch(() => undefined);
      }

      const effectiveKind = prefill.document_kind || document.document_kind;
      if (
        document.processing_status === "extracted" &&
        ["egrul_extract", "egrip_extract", "unknown_registry_extract"].includes(effectiveKind)
      ) {
        await api.post(`/source-documents/${document.id}/extract`).catch(() => undefined);
      }

      const values = prefill.prefill || {};
      const extractedSignatoryName = [
        values.signatory_last_name,
        values.signatory_first_name,
        values.signatory_middle_name,
      ].filter(Boolean).join(" ");
      const changed = Object.values(values).filter((value) => Boolean(value?.trim())).length;

      // Экран загрузки и экран проверки — разные экземпляры формы. Поэтому
      // распознанные реквизиты сохраняем сразу: иначе при переходе по вкладке
      // временное состояние терялось, хотя пользователь видел успешный разбор.
      // На следующем экране значения всё равно остаются редактируемыми и
      // должны быть сверены с документом.
      await Promise.all([
        client && changed
          ? api.put(`/clients/${client.id}`, {
              type: prefill.client_type || client.type,
              full_name_or_company_name: values.name?.trim() || client.fullNameOrCompanyName,
              short_name: values.short_name?.trim() || client.shortName || null,
              inn: values.inn?.trim() || client.inn || null,
              ogrn_or_ogrnip: values.ogrn?.trim() || client.ogrnOrOgrnip || null,
              kpp: values.kpp?.trim() || client.kpp || null,
              address: values.address?.trim() || client.address || null,
            })
          : Promise.resolve(),
        extractedSignatoryName || values.signatory_position?.trim() || values.business_activity?.trim()
          ? api.put(`/applications/${application.id}`, {
              signatory_name: extractedSignatoryName || application.signatoryName || null,
              signatory_position: values.signatory_position?.trim() || application.signatoryPosition || null,
              business_description: values.business_activity?.trim() || application.businessDescription || null,
              goods_services_raw: values.business_activity?.trim() || application.goodsServicesRaw || null,
            })
          : Promise.resolve(),
      ]);
      setForm((current) => ({
        ...current,
        name: values.name?.trim() || current.name,
        inn: values.inn?.trim() || current.inn,
        ogrn: values.ogrn?.trim() || current.ogrn,
        kpp: values.kpp?.trim() || current.kpp,
        address: values.address?.trim() || current.address,
        business: values.business_activity?.trim() || current.business,
        signatoryName: extractedSignatoryName || current.signatoryName,
        signatoryPosition: values.signatory_position?.trim() || current.signatoryPosition,
      }));

      await loadApplicantDocuments();
      if (changed) await onSaved();
      filingRules.reload();
      toast({
        title: changed ? "Данные перенесены в форму" : "Документ добавлен",
        description: changed
          ? `Обновлено полей: ${changed}. Проверьте их и при необходимости исправьте перед продолжением.`
          : prefill.warning || "Автозаполнение для этого документа недоступно — заполните сведения ниже вручную.",
      });
    } catch (error) {
      toast({
        title: "Не удалось обработать документ",
        description: messageOf(error, "Проверьте файл и попробуйте ещё раз"),
        variant: "destructive",
      });
    } finally {
      setApplicantDocumentUploading(false);
      if (applicantDocumentInput.current) applicantDocumentInput.current.value = "";
    }
  };

  const buildDescription = (current = form) => {
    const text = (current.markText || current.markName).replace(/\s+/g, " ").trim();
    const quotedText = text ? ` «${text}»` : "";
    const alphabet = text
      ? /[А-ЯЁ]/i.test(text) && /[A-Z]/i.test(text)
        ? "буквами кириллического и латинского алфавитов"
        : /[А-ЯЁ]/i.test(text)
          ? "буквами кириллического алфавита"
          : /[A-Z]/i.test(text)
            ? "буквами латинского алфавита"
            : "с использованием букв, цифр и иных символов"
      : "";
    const letterCase = text && /[А-ЯЁA-Z]/.test(text) && !/[а-яёa-z]/.test(text)
      ? "заглавными "
      : "";
    const colorSentence = current.colors.trim()
      ? ` Обозначение выполнено в следующем цветовом сочетании: ${current.colors.trim()}.`
      : "";
    const descriptions: Record<MarkType, string> = {
      word: `Словесное обозначение${quotedText}${alphabet ? `, выполненное ${letterCase}${alphabet}` : ""}.`,
      figurative: `Изобразительное обозначение представляет собой графическую композицию, внешний вид и расположение элементов которой приведены в заявленном изображении.${colorSentence}`,
      combined: `Комбинированное обозначение включает словесный элемент${quotedText}${alphabet ? `, выполненный ${letterCase}${alphabet}` : ""}. Графическое исполнение и взаимное расположение элементов приведены в заявленном изображении.${colorSentence}`,
      "3d": `Объёмное обозначение представляет собой трёхмерную форму, внешний вид которой приведён в приложенных изображениях с разных ракурсов.${colorSentence}`,
      sound: "Звуковое обозначение представляет собой последовательность звуков, воспроизводимую в приложенной аудиозаписи.",
      color: current.colors.trim()
        ? `Обозначение представляет собой сочетание цветов: ${current.colors.trim()}. Расположение цветов приведено в заявленном изображении.`
        : "Обозначение представляет собой цвет или сочетание цветов, расположение которых приведено в заявленном изображении.",
      other: `Обозначение${quotedText}. Существенные элементы и способ воспроизведения обозначения приведены в приложенных материалах.${colorSentence}`,
    };
    return descriptions[current.markType];
  };

  const generateDescription = () => {
    set("description", buildDescription());
    toast({ title: "Описание подготовлено", description: "Проверьте формулировку и при необходимости дополните её." });
  };

  const colorName = (hex: string) => {
    const value = hex.replace("#", "");
    if (!/^[0-9a-f]{6}$/i.test(value)) return hex;
    const [r, g, b] = [0, 2, 4].map((offset) => Number.parseInt(value.slice(offset, offset + 2), 16));
    const max = Math.max(r, g, b); const min = Math.min(r, g, b);
    if (max < 45) return "чёрный";
    if (min > 235) return "белый";
    if (max - min < 25) return max < 140 ? "серый" : "светло-серый";
    if (r > 170 && g > 70 && b < 110) return "оранжевый";
    if (r > 150 && b > 130 && g < 130) return "фиолетовый";
    if (r === max && g < 150) return "красный";
    if (g === max && b > 120) return "бирюзовый";
    if (g === max) return "зелёный";
    if (b === max && r < 100) return max < 145 ? "тёмно-синий" : "синий";
    return hex.toUpperCase();
  };

  const colorsFromImage = (image: MarkImageDto | null) => {
    const detected = Array.from(
      new Set((image?.dominant_colors || []).map(colorName)),
    ).filter((value) => !value.startsWith("#"));
    const neutral = new Set(["чёрный", "белый", "серый", "светло-серый"]);
    const chromatic = detected.filter((value) => !neutral.has(value));
    return (chromatic.length > 0 ? chromatic : detected).slice(0, 6).join(", ");
  };

  const generateAllDetails = async () => {
    setAutoFilling(true);
    try {
      await api.put(`/applications/${application.id}`, {
        mark_name: form.markName.trim(),
        mark_text: (form.markText || form.markName).trim(),
        mark_type: form.markType,
      });
      const [languageResult, visualResult] = await Promise.allSettled([
        api.post<{ transliteration: string | null; translation: string | null }>(
          `/applications/${application.id}/suggest-mark-language`,
        ),
        imageMark && markImage
          ? api.post<MarkDescriptionDto>(`/applications/${application.id}/generate-mark-description`)
          : Promise.resolve(null),
      ]);
      const language = languageResult.status === "fulfilled"
        ? languageResult.value
        : { transliteration: null, translation: null };
      const visual = visualResult.status === "fulfilled" ? visualResult.value : null;
      const deterministicTransliteration = transliterateRussian(form.markText || form.markName);
      const colorClaim = visual?.colors?.join(", ") || colorsFromImage(markImage);
      const enriched = { ...form, colors: colorClaim };
      const suggested = {
        colors: colorClaim,
        // Для изображения нельзя подменять анализ общим шаблоном: фраза
        // «элементы приведены на изображении» выглядит как готовый результат,
        // хотя модель картинку не увидела.
        description: visual?.description
          || (imageMark && hasGenericImageDescription(form.description) ? "" : form.description)
          || (!imageMark ? buildDescription(enriched) : ""),
        // Для монохромного знака поле (591) оставляется пустым. Старое
        // противоречащее изображению значение намеренно заменяется.
        transliteration: deterministicTransliteration || visual?.transliteration || language.transliteration || "",
        translation: visual?.translation || language.translation || "",
      };
      setForm((current) => ({ ...current, ...suggested }));
      await api.post(`/applications/${application.id}/mark-details-suggestions`, suggested);
      toast({
        title: imageMark && !visual ? "Изображение пока не проанализировано" : "Сведения подготовлены",
        description: visual
          ? "Изображение проанализировано. Проверьте описание и цвета перед сохранением."
          : imageMark
            ? messageOf(
                visualResult.status === "rejected" ? visualResult.reason : null,
                "Внешняя модель не ответила. Мы не стали подменять анализ общим шаблоном — повторите попытку позже.",
              )
            : "Проверьте предложения системы перед сохранением.",
        variant: imageMark && !visual ? "destructive" : undefined,
      });
    } catch (error) {
      if (!imageMark) generateDescription();
      toast({ title: "Не удалось подготовить сведения", description: messageOf(error, "Попробуйте ещё раз позже"), variant: "destructive" });
    } finally {
      setAutoFilling(false);
    }
  };

  const refreshPreview = async () => {
    const blob = await api.blob(`/applications/${application.id}/mark-image/content`);
    const nextUrl = URL.createObjectURL(blob);
    setPreviewUrl((previous) => {
      if (previous) URL.revokeObjectURL(previous);
      return nextUrl;
    });
  };

  useEffect(() => {
    let active = true;
    api.get<MarkImageDto>(`/applications/${application.id}/mark-image`)
      .then(async (image) => {
        if (!active) return;
        setMarkImage(image);
        await refreshPreview();
      })
      .catch(() => undefined);
    return () => { active = false; };
  }, [application.id]);

  useEffect(() => {
    if (
      mode === "review"
      && imageMark
      && markImage
      && hasGenericImageDescription(form.description)
      && !automaticDescriptionRequested.current
    ) {
      automaticDescriptionRequested.current = true;
      void generateAllDetails();
    }
  }, [mode, imageMark, markImage?.document_id]);

  useEffect(() => {
    loadApplicantDocuments()
      .catch(() => undefined);
  }, [application.id]);

  useEffect(() => {
    loadRepresentative().catch(() => undefined);
  }, [application.id, application.representativeId, client?.id, mode]);

  useEffect(() => () => {
    if (previewUrl) URL.revokeObjectURL(previewUrl);
  }, [previewUrl]);

  const uploadMarkImage = async (file?: File) => {
    if (!file) return;
    setImageUploading(true);
    try {
      // Сервер проверяет соответствие файла виду знака, поэтому сохраняем
      // выбранный пользователем вид непосредственно перед загрузкой.
      await api.put(`/applications/${application.id}`, { mark_type: form.markType });
      const image = await api.upload<MarkImageDto>(
        `/applications/${application.id}/mark-image`, file,
      );
      setMarkImage(image);
      setForm((current) => ({
          ...current,
          markText: current.markType === "combined" && image.recognized_text.trim()
          ? image.recognized_text.replace(/\s+/g, " ").trim()
          : current.markText,
          colors: colorsFromImage(image) || current.colors,
      }));
      await refreshPreview();
      toast({ title: "Изображение обработано", description: image.recognized_text ? "Проверьте распознанный текст." : "Текст не найден — это нормально для графического знака." });
    } catch (error) {
      toast({ title: "Не удалось загрузить изображение", description: messageOf(error, "Проверьте PNG или JPEG"), variant: "destructive" });
    } finally { setImageUploading(false); }
  };

  const removeMarkImage = async () => {
    try {
      await api.delete(`/applications/${application.id}/mark-image`);
      setMarkImage(null);
      setPreviewUrl((previous) => { if (previous) URL.revokeObjectURL(previous); return null; });
      toast({ title: "Изображение удалено из обозначения" });
    } catch (error) {
      toast({ title: "Не удалось удалить изображение", description: messageOf(error, "Попробуйте ещё раз"), variant: "destructive" });
    }
  };

  const uploadMarkAudio = async (file?: File) => {
    if (!file) return;
    setAudioUploading(true);
    try {
      await api.put(`/applications/${application.id}`, { mark_type: form.markType });
      const document = await api.upload<SourceDocumentDto>(`/applications/${application.id}/source-documents`, file);
      setMarkAudio(document);
      toast({ title: "Аудиозапись загружена", description: "Проверьте и дополните текстовое описание звучания." });
    } catch (error) {
      toast({ title: "Не удалось загрузить аудиозапись", description: messageOf(error, "Используйте MP3 или WAV"), variant: "destructive" });
    } finally { setAudioUploading(false); }
  };

  const persistForm = async () => {
    if (mode === "upload") {
      await Promise.all([
        api.put(`/applications/${application.id}`, {
          mark_name: form.markName.trim(),
          mark_text: form.markType === "figurative" ? "" : (form.markText || form.markName).trim(),
          mark_type: form.markType,
          business_description: form.business.trim() || null,
          goods_services_raw: form.goods.trim() || form.business.trim() || null,
          description_of_mark: form.description.trim() || null,
          colors_claimed: form.colors.trim() || null,
          transliteration: form.transliteration.trim() || null,
          translation: form.translation.trim() || null,
          request_paper_certificate: form.requestPaperCertificate,
        }),
        client ? api.put(`/clients/${client.id}`, {
          full_name_or_company_name: form.name.trim() || client.fullNameOrCompanyName,
          inn: form.inn.trim() || null,
          ogrn_or_ogrnip: form.ogrn.trim() || null,
          kpp: form.kpp.trim() || null,
          address: form.address.trim() || null,
          country: form.country || "RU",
          email: form.email.trim() || null,
          phone: form.phone.trim() || null,
        }) : Promise.resolve(),
      ]);
      return;
    }
    let representativeId: number | null = null;
    if (usesRepresentative && client) {
      const payload = {
        full_name: representative.fullName.trim(),
        email: representative.email.trim() || null,
        phone: representative.phone.trim() || null,
        address: representative.address.trim() || null,
        role: representative.isPatentAttorney
          ? "Патентный поверенный"
          : representative.role.trim() || "Иной представитель",
        is_patent_attorney: representative.isPatentAttorney,
        patent_attorney_registration_number: representative.isPatentAttorney
          ? representative.registrationNumber.trim() || null
          : null,
        authority_type: representative.authorityType,
        poa_reference: representative.authorityType === "power_of_attorney"
          ? representative.poaReference.trim() || null
          : null,
        personal_data_consent_reference: null,
      };
      const savedRepresentative = representative.id
        ? await api.put<RepresentativeDto>(
            `/clients/${client.id}/representatives/${representative.id}`,
            payload,
          )
        : await api.post<RepresentativeDto>(`/clients/${client.id}/representatives`, payload);
      representativeId = savedRepresentative.id;
      if (representative.id !== savedRepresentative.id) {
        setRepresentative((current) => ({ ...current, id: savedRepresentative.id }));
      }
    }

    await Promise.all([
      client ? api.put(`/clients/${client.id}`, {
        full_name_or_company_name: form.name.trim(), inn: form.inn.trim() || null,
        ogrn_or_ogrnip: form.ogrn.trim() || null, address: form.address.trim() || null,
        kpp: form.kpp.trim() || null,
        country: form.country || "RU", email: form.email.trim() || null, phone: form.phone.trim() || null,
      }) : Promise.resolve(),
      api.put(`/applications/${application.id}`, {
        mark_name: form.markName.trim(),
        mark_text: form.markType === "figurative" ? "" : (form.markType === "combined" ? form.markText.trim() : form.markName.trim()),
        mark_type: form.markType,
        business_description: activityDescription.trim() || null, goods_services_raw: activityDescription.trim() || null,
        description_of_mark: form.description.trim() || null, colors_claimed: form.colors.trim() || null,
        transliteration: form.transliteration.trim() || null, translation: form.translation.trim() || null,
        territory: COUNTRY_OPTIONS.find((item) => item.code === form.country)?.name || "Россия",
        filing_method: form.filingMethod,
        request_paper_certificate: form.requestPaperCertificate,
        signatory_name: form.signatoryName.trim() || null,
        signatory_position: form.signatoryPosition.trim() || null,
        signature_date: form.signatureDate || null,
        representative_id: representativeId,
      }),
    ]);
  };

  const formSnapshot = JSON.stringify({ form, usesRepresentative, representative });
  useEffect(() => {
    if (mode !== "review") return;
    api.get<{ confirmed: boolean }>(`/applications/${application.id}/data-confirmation`)
      .then((result) => setDataConfirmed(result.confirmed))
      .catch(() => setDataConfirmed(false));
  }, [application.id, mode]);

  useEffect(() => {
    if (!autosaveReady.current) {
      autosaveReady.current = true;
      lastSavedSnapshot.current = formSnapshot;
      return;
    }
    if (formSnapshot === lastSavedSnapshot.current) return;
    setAutosaveStatus("dirty");
    setDataConfirmed(false);
    if (!form.markName.trim() || (mode === "review" && !form.name.trim())) return;
    if (autosaveTimer.current !== null) window.clearTimeout(autosaveTimer.current);
    autosaveTimer.current = window.setTimeout(async () => {
      setAutosaveStatus("saving");
      try {
        await persistForm();
        lastSavedSnapshot.current = formSnapshot;
        setAutosaveStatus("saved");
        filingRules.reload();
      } catch {
        setAutosaveStatus("error");
      }
    }, 1000);
    return () => {
      if (autosaveTimer.current !== null) window.clearTimeout(autosaveTimer.current);
    };
  }, [formSnapshot]);

  const save = async (): Promise<boolean> => {
    if (!form.markName.trim()) {
      toast({ title: "Укажите обозначение", description: "Введите название знака или короткое рабочее название.", variant: "destructive" });
      return false;
    }
    if (mode === "review" && !form.name.trim()) {
      toast({ title: "Укажите заявителя", description: "Наименование организации или ФИО нужны для заявления.", variant: "destructive" });
      return false;
    }
    if (mode === "review" && !form.signatoryName.trim()) {
      toast({ title: "Укажите подписанта", description: "Нужно ФИО человека, который подпишет заявление.", variant: "destructive" });
      return false;
    }
    if (mode === "review" && client?.type === "company" && !form.signatoryPosition.trim()) {
      toast({ title: "Укажите должность подписанта", description: "Например: генеральный директор или представитель по доверенности.", variant: "destructive" });
      return false;
    }
    if (mode === "review" && !form.signatureDate) {
      toast({ title: "Укажите дату подписания", description: "По умолчанию установлена сегодняшняя дата; при необходимости измените её.", variant: "destructive" });
      return false;
    }
    if (mode === "review" && usesRepresentative && !representative.fullName.trim()) {
      toast({ title: "Укажите представителя", description: "Нужно ФИО человека, который будет вести заявку.", variant: "destructive" });
      return false;
    }
    if (mode === "review" && usesRepresentative && !representative.address.trim()) {
      toast({ title: "Укажите адрес представителя", description: "Этот адрес будет использоваться для переписки по заявке.", variant: "destructive" });
      return false;
    }
    if (mode === "review" && usesRepresentative && representative.isPatentAttorney && !representative.registrationNumber.trim()) {
      toast({ title: "Укажите номер патентного поверенного", description: "Введите регистрационный номер из реестра патентных поверенных.", variant: "destructive" });
      return false;
    }
    if (mode === "review" && usesRepresentative && representative.authorityType === "power_of_attorney" && !representative.poaReference.trim()) {
      toast({ title: "Укажите реквизиты доверенности", description: "Например: № 12 от 28.08.2026.", variant: "destructive" });
      return false;
    }
    if (mode === "review" && usesRepresentative && representative.authorityType === "power_of_attorney" && !powerOfAttorneyDocument) {
      toast({ title: "Приложите доверенность", description: "Файл доверенности должен войти в пакет для подачи.", variant: "destructive" });
      return false;
    }
    if (imageMark && !markImage) {
      toast({ title: "Загрузите изображение знака", description: "Оно обязательно для изобразительного и комбинированного обозначения.", variant: "destructive" });
      return false;
    }
    if (soundMark && !markAudio) {
      toast({ title: "Загрузите аудиозапись знака", description: "Для звукового обозначения нужен файл MP3 или WAV.", variant: "destructive" });
      return false;
    }
    setSaving(true);
    try {
      if (autosaveTimer.current !== null) window.clearTimeout(autosaveTimer.current);
      if (lastSavedSnapshot.current !== formSnapshot || autosaveStatus === "error") {
        setAutosaveStatus("saving");
        await persistForm();
        lastSavedSnapshot.current = formSnapshot;
        setAutosaveStatus("saved");
      }
      filingRules.reload();
      if (mode === "upload") {
        toast({ title: "Материалы сохранены", description: "Теперь проверьте сведения, которые система подготовила для заявления." });
        await onSaved();
        onNext?.();
        return true;
      }
      toast({ title: "Данные сохранены" });
      await onSaved();
      onNext?.();
      return true;
    } catch (error) {
      setAutosaveStatus("error");
      toast({ title: "Не удалось сохранить", description: messageOf(error, "Попробуйте ещё раз"), variant: "destructive" });
      return false;
    } finally { setSaving(false); }
  };

  const saveApplicantToProfile = async () => {
    if (!form.name.trim()) {
      toast({
        title: "Укажите заявителя",
        description: "Сначала заполните наименование организации или ФИО.",
        variant: "destructive",
      });
      return;
    }
    setSavingProfile(true);
    try {
      await api.patch("/auth/me", {
        applicant_profile_json: {
          type: applicantType || "individual",
          full_name_or_company_name: form.name.trim(),
          inn: form.inn.trim() || null,
          ogrn_or_ogrnip: form.ogrn.trim() || null,
          kpp: form.kpp.trim() || null,
          address: form.address.trim() || null,
          country: form.country || "RU",
          email: form.email.trim() || null,
          phone: form.phone.trim() || null,
        },
      });
      await refreshProfile();
      toast({
        title: "Данные заявителя запомнены",
        description: "В следующей заявке эти поля заполнятся автоматически.",
      });
    } catch (error) {
      toast({
        title: "Не удалось сохранить данные в профиль",
        description: messageOf(error, "Попробуйте ещё раз"),
        variant: "destructive",
      });
    } finally {
      setSavingProfile(false);
    }
  };

  const confirmReviewedData = async () => {
    setConfirmingData(true);
    try {
      if (autosaveTimer.current !== null) window.clearTimeout(autosaveTimer.current);
      if (lastSavedSnapshot.current !== formSnapshot) {
        setAutosaveStatus("saving");
        await persistForm();
        lastSavedSnapshot.current = formSnapshot;
        setAutosaveStatus("saved");
      }
      filingRules.reload();
      const result = await api.post<{ confirmed: boolean }>(`/applications/${application.id}/data-confirmation`);
      setDataConfirmed(result.confirmed);
      toast({ title: "Сведения подтверждены", description: "Если вы измените данные, система попросит проверить их ещё раз." });
    } catch (error) {
      setDataConfirmed(false);
      toast({ title: "Не удалось подтвердить сведения", description: messageOf(error, "Попробуйте ещё раз"), variant: "destructive" });
    } finally {
      setConfirmingData(false);
    }
  };

  const incompleteReviewItems = mode === "review" ? [
    !form.name.trim() ? { label: "Указать заявителя", target: "applicant-data" } : null,
    !form.address.trim() ? { label: "Проверить адрес", target: "applicant-data" } : null,
    !form.signatoryName.trim() ? { label: "Указать подписанта", target: "signatory-data" } : null,
    client?.type === "company" && !form.signatoryPosition.trim() ? { label: "Указать должность подписанта", target: "signatory-data" } : null,
    usesRepresentative && !representative.fullName.trim() ? { label: "Указать представителя", target: "representative-data" } : null,
    usesRepresentative && !representative.address.trim() ? { label: "Указать адрес представителя", target: "representative-data" } : null,
    usesRepresentative && representative.isPatentAttorney && !representative.registrationNumber.trim() ? { label: "Указать номер поверенного", target: "representative-data" } : null,
    usesRepresentative && representative.authorityType === "power_of_attorney" && !representative.poaReference.trim() ? { label: "Указать доверенность", target: "representative-data" } : null,
    usesRepresentative && representative.authorityType === "power_of_attorney" && !powerOfAttorneyDocument ? { label: "Приложить доверенность", target: "representative-data" } : null,
    !form.markName.trim() ? { label: "Указать обозначение", target: "mark-data" } : null,
    !activityDescription.trim() ? { label: "Описать товары или услуги", target: "mark-data" } : null,
    imageMark && !markImage ? { label: "Загрузить изображение", target: "mark-data" } : null,
    soundMark && !markAudio ? { label: "Загрузить аудиозапись", target: "mark-data" } : null,
  ].filter((item): item is { label: string; target: string } => Boolean(item)) : [];

  const scrollTo = (target: string) => {
    document.getElementById(target)?.scrollIntoView({ behavior: "smooth", block: "start" });
  };

  return (
    <ClientPanel
      title={mode === "upload" ? "Загрузите материалы" : "Проверьте сведения для заявки"}
      description={mode === "upload"
        ? "Добавьте документы заявителя и сам товарный знак. Система прочитает доступные сведения и покажет их на следующем экране."
        : "Здесь собрана вся информация, которая пойдёт в заявление. Проверьте реквизиты, описание знака и товары или услуги; всё можно исправить."}
    >
      <div className="mb-5 flex min-h-7 justify-end" aria-live="polite">
        {autosaveStatus !== "idle" && (
          <span className={cn(
            "inline-flex items-center gap-2 rounded-full px-3 py-1 text-xs font-semibold",
            autosaveStatus === "error" ? "bg-red-50 text-red-700" : "bg-[#eef9f8] text-[#087c78]",
          )}>
            {autosaveStatus === "saving" ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : autosaveStatus === "saved" ? <CheckCircle2 className="h-3.5 w-3.5" /> : <Circle className="h-3.5 w-3.5" />}
            {autosaveStatus === "dirty" ? "Есть несохранённые изменения" : autosaveStatus === "saving" ? "Сохраняем изменения…" : autosaveStatus === "saved" ? "Все изменения сохранены" : "Не удалось сохранить автоматически"}
          </span>
        )}
      </div>
      {mode === "review" && (
        <section className={cn(
          "mb-6 rounded-[1.2rem] border p-4 sm:p-5",
          incompleteReviewItems.length ? "border-amber-200 bg-amber-50" : "border-emerald-200 bg-emerald-50",
        )}>
          <div className="flex items-start gap-3">
            {incompleteReviewItems.length ? <AlertCircle className="mt-0.5 h-5 w-5 shrink-0 text-amber-700" /> : <CheckCircle2 className="mt-0.5 h-5 w-5 shrink-0 text-emerald-700" />}
            <div>
              <p className="font-semibold text-[#11113f]">{incompleteReviewItems.length ? `Перед анализом осталось: ${incompleteReviewItems.length}` : "Основные сведения заполнены"}</p>
              <p className="mt-1 text-sm leading-relaxed text-[#5f6072]">{incompleteReviewItems.length ? "Нажмите на пункт — экран прокрутится к нужному разделу." : "Теперь проверьте предложенные классы товаров и услуг."}</p>
              <div className="mt-3 flex flex-wrap gap-2">
                {incompleteReviewItems.map((item) => <button key={item.label} type="button" onClick={() => scrollTo(item.target)} className="rounded-full border border-amber-300 bg-white px-3 py-1.5 text-xs font-semibold text-amber-900 hover:border-amber-500">{item.label}</button>)}
                {incompleteReviewItems.length === 0 && <button type="button" onClick={() => scrollTo("class-confirmation")} className="rounded-full bg-emerald-700 px-4 py-2 text-xs font-semibold text-white hover:bg-emerald-800">Перейти к классам</button>}
              </div>
            </div>
          </div>
        </section>
      )}
      {mode === "upload" && <section className="mb-8 rounded-[1.3rem] border-2 border-[#0d9f9b]/25 bg-[#eef9f8] p-5 sm:p-6">
        <div className="flex flex-col gap-4 sm:flex-row sm:items-start sm:justify-between">
          <div className="max-w-2xl">
            <div className="flex items-center gap-3">
              <span className="flex h-10 w-10 shrink-0 items-center justify-center rounded-full bg-white text-[#0d9f9b]">
                <FileText className="h-5 w-5" />
              </span>
              <div>
                <h3 className="text-xl font-semibold text-[#11113f]">Загрузите документы заявителя</h3>
                <p className="mt-1 text-sm leading-relaxed text-[#5f6072]">
                  Выписка ЕГРЮЛ или ЕГРИП заполнит реквизиты организации или ИП. Из паспорта физлица система предложит только ФИО и адрес — остальные паспортные данные в заявление не переносятся.
                </p>
              </div>
            </div>
          </div>
          <Button
            type="button"
            disabled={applicantDocumentUploading}
            onClick={() => applicantDocumentInput.current?.click()}
            className="shrink-0 rounded-full bg-[#0d9f9b] px-5 hover:bg-[#078984]"
            data-testid="button-upload-applicant-document"
          >
            {applicantDocumentUploading ? <Loader2 className="h-4 w-4 animate-spin" /> : <Upload className="h-4 w-4" />}
            {applicantDocumentUploading ? "Обрабатываем…" : "Добавить документ"}
          </Button>
          <input
            ref={applicantDocumentInput}
            type="file"
            className="hidden"
            accept=".pdf,.docx,.txt,.png,.jpg,.jpeg"
            onChange={(event) => void uploadApplicantDocument(event.target.files?.[0])}
            data-testid="input-applicant-document"
          />
        </div>

        {applicantDocuments.length > 0 && (
          <div className="mt-5 space-y-2">
            {applicantDocuments.map((document) => (
              <div key={document.id} className="flex flex-col gap-2 rounded-xl border border-[#11113f]/10 bg-white px-4 py-3 sm:flex-row sm:items-center sm:justify-between">
                <div className="min-w-0">
                  <p className="truncate text-sm font-semibold text-[#11113f]">{document.original_filename}</p>
                  <p className="mt-0.5 text-xs text-[#6d6d7d]">
                    {DOCUMENT_KIND_LABELS[document.document_kind] || "Документ"} · {document.processing_status === "failed" ? "нужно проверить файл" : "файл обработан"}
                  </p>
                  {document.document_kind === "passport" && <p className="mt-1 text-xs font-medium text-sky-800">Чувствительный документ: хранится только для сверки и не войдёт в ZIP.</p>}
                </div>
                <span className="w-fit rounded-full bg-emerald-100 px-2.5 py-1 text-[11px] font-bold text-emerald-800">Добавлен в заявку</span>
              </div>
            ))}
          </div>
        )}

        <p className="mt-4 flex items-start gap-2 text-xs leading-relaxed text-[#5f6072]">
          <CheckCircle2 className="mt-0.5 h-4 w-4 shrink-0 text-[#0d9f9b]" />
          После загрузки проверьте обновившиеся поля ниже. На следующий шаг попадут именно значения, которые вы сохраните здесь.
        </p>
      </section>}
      <div className="space-y-6">
        {mode === "review" && <FormGroup step={1} id="applicant-data" title={<span className="inline-flex items-center gap-1">О заявителе <HelpTip text="Заявитель — человек, ИП или организация, на имя которых будет зарегистрирован товарный знак. После регистрации именно заявитель станет правообладателем." /></span>} hint="Эти сведения попадут в заявление как данные правообладателя">
          <MarkedField label="Наименование или ФИО" source={sourceFor("applicant_name", Boolean(form.name))}><Input value={form.name} onChange={(e) => set("name", e.target.value)} /></MarkedField>
          <div className="grid gap-4 sm:grid-cols-3">
            {isApplicable("applicant_inn", true) && <MarkedField label="ИНН" source={sourceFor("applicant_inn", Boolean(form.inn))}><Input value={form.inn} onChange={(e) => set("inn", e.target.value)} /></MarkedField>}
            {isApplicable("applicant_registry_number", client?.type !== "individual") && <MarkedField label={applicantType === "sole_proprietor" ? "ОГРНИП" : "ОГРН"} source={sourceFor("applicant_registry_number", Boolean(form.ogrn))}><Input value={form.ogrn} onChange={(e) => set("ogrn", e.target.value)} /></MarkedField>}
            {isApplicable("applicant_kpp", client?.type === "company") && <MarkedField label="КПП" source={sourceFor("applicant_kpp", Boolean(form.kpp))}><Input value={form.kpp} onChange={(e) => set("kpp", e.target.value)} /></MarkedField>}
          </div>
          <MarkedField label="Адрес" source={sourceFor("applicant_address", Boolean(form.address))}><Input value={form.address} onChange={(e) => set("address", e.target.value)} /></MarkedField>
          <MarkedField label={<span className="inline-flex items-center gap-1">Код страны <HelpTip text="Двухбуквенный код страны заявителя по стандарту ВОИС ST.3. Для заявителей из России используется RU." /></span>} source={sourceFor("territory", Boolean(form.country))}>
            <select value={form.country} onChange={(event) => set("country", event.target.value)} className="flex h-10 w-full rounded-md border border-input bg-background px-3 py-2 text-sm ring-offset-background focus:outline-none focus:ring-2 focus:ring-ring focus:ring-offset-2">
              {COUNTRY_OPTIONS.map((country) => <option key={country.code} value={country.code}>{country.name} — {country.code}</option>)}
            </select>
          </MarkedField>
          <div className="grid gap-4 sm:grid-cols-2">
            <MarkedField label="E-mail для переписки" source={sourceFor("applicant_email", Boolean(form.email))}><Input type="email" value={form.email} onChange={(e) => set("email", e.target.value)} /></MarkedField>
            <MarkedField label="Телефон для переписки" source={sourceFor("applicant_phone", Boolean(form.phone))}><Input value={form.phone} onChange={(e) => set("phone", e.target.value)} /></MarkedField>
          </div>
          <p className="text-xs leading-relaxed text-[#6d6d7d]">Адрес, телефон и e-mail будут использованы в черновике как контакты для переписки с Роспатентом.</p>
          {user?.role === "client" && (
            <div className={cn(
              "flex flex-col gap-4 rounded-2xl border-2 p-4 shadow-sm sm:flex-row sm:items-center sm:justify-between sm:p-5",
              profileMatchesForm
                ? "border-[#0d9f9b]/45 bg-gradient-to-r from-[#e5f8f6] to-[#f2fbfa]"
                : "border-amber-300 bg-amber-50",
            )}>
              <div className="flex items-start gap-3">
                <span className={cn(
                  "flex h-10 w-10 shrink-0 items-center justify-center rounded-full",
                  profileMatchesForm ? "bg-[#0d9f9b] text-white" : "bg-amber-200 text-amber-900",
                )}>
                  <CheckCircle2 className="h-5 w-5" />
                </span>
                <div>
                <p className="text-sm font-semibold text-[#11113f]">
                  {profileMatchesForm ? "Данные сохранены для следующих заявок" : "Запомнить данные для следующих заявок?"}
                </p>
                <p className="mt-1 text-xs leading-relaxed text-[#5f6072]">
                  Сохраним только реквизиты заявителя и контакты. Данные товарного знака останутся только в этой заявке.
                </p>
                </div>
              </div>
              {profileMatchesForm ? (
                <span className="inline-flex w-fit shrink-0 items-center gap-2 rounded-full bg-[#087c78] px-5 py-2.5 text-sm font-bold text-white shadow-sm">
                  <CheckCircle2 className="h-4 w-4" />
                  Сохранено в профиле
                </span>
              ) : (
                <Button
                  type="button"
                  disabled={savingProfile}
                  onClick={() => void saveApplicantToProfile()}
                  className="shrink-0 rounded-full bg-[#0d9f9b] px-5 text-white hover:bg-[#087c78]"
                  data-testid="save-applicant-to-profile"
                >
                  {savingProfile ? <Loader2 className="h-4 w-4 animate-spin" /> : <CheckCircle2 className="h-4 w-4" />}
                  {savingProfile ? "Сохраняем…" : "Запомнить данные"}
                </Button>
              )}
            </div>
          )}
        </FormGroup>}

        {mode === "review" && <FormGroup step={2} id="signatory-data" title="Кто подпишет заявление" hint="Это человек, чьей подписью будет заверена подача. Для организации обычно это руководитель; представитель по доверенности указывается отдельно на следующем шаге">
            <div className="mt-4 space-y-4">
              <MarkedField label="Способ подачи" source={sourceFor("filing_method", Boolean(form.filingMethod))}>
                <Select value={form.filingMethod} onValueChange={(value) => set("filingMethod", value)}><SelectTrigger><SelectValue /></SelectTrigger><SelectContent><SelectItem value="electronic">Электронно через официальный сервис</SelectItem><SelectItem value="paper">На бумаге</SelectItem></SelectContent></Select>
              </MarkedField>
              <label className="flex cursor-pointer items-start gap-3 rounded-xl border border-[#11113f]/10 bg-white p-4">
                <Checkbox
                  checked={form.requestPaperCertificate}
                  onCheckedChange={(checked) => setForm((current) => ({ ...current, requestPaperCertificate: checked === true }))}
                />
                <span>
                  <span className="flex flex-wrap items-center gap-2 text-sm font-semibold text-[#11113f]">Получить свидетельство на бумаге <SourceBadge source={sourceFor("paper_certificate", true)} /></span>
                  <span className="mt-1 block text-xs leading-relaxed text-[#6d6d7d]">Необязательно. Электронное свидетельство выдаётся в любом случае; бумажный экземпляр увеличит пошлину на 3 000 ₽.</span>
                </span>
              </label>
              <MarkedField label="ФИО подписанта" source={sourceFor("signatory_name", Boolean(form.signatoryName))}><Input value={form.signatoryName} onChange={(event) => set("signatoryName", event.target.value)} placeholder="Например: Иванов Иван Иванович" /></MarkedField>
              {isApplicable("signatory_position", client?.type === "company") && <MarkedField label="Должность" source={sourceFor("signatory_position", Boolean(form.signatoryPosition))}><Input value={form.signatoryPosition} onChange={(event) => set("signatoryPosition", event.target.value)} placeholder="Например: генеральный директор" /></MarkedField>}
              <MarkedField label="Дата подписания" source={sourceFor("signature_date", Boolean(form.signatureDate))}><Input type="date" value={form.signatureDate} onChange={(event) => set("signatureDate", event.target.value)} /></MarkedField>
              <div className="rounded-lg bg-[#eef9f8] p-3 text-xs leading-relaxed text-[#315c5a]">{form.filingMethod === "electronic" ? "Рисовать подпись здесь не нужно. При отправке заявление подписывается электронной подписью в официальном сервисе Роспатента." : "Скачайте и распечатайте заявление, затем поставьте собственноручную подпись в оставленном поле. Картинка или нарисованная мышкой подпись её не заменяет."}</div>
            </div>
        </FormGroup>}

        {mode === "review" && <FormGroup step={3} id="representative-data" title="Кто будет вести заявку" hint="Если вы подаёте сами, дополнительные сведения не нужны. Если от вашего имени действует другой человек, укажите его здесь">
          <div className="mt-4 space-y-4">
            <div className="grid gap-3 sm:grid-cols-2">
              <button
                type="button"
                onClick={() => setUsesRepresentative(false)}
                className={cn(
                  "rounded-xl border p-4 text-left transition-colors",
                  !usesRepresentative ? "border-[#0d9f9b] bg-[#eef9f8]" : "border-[#11113f]/10 bg-white hover:border-[#0d9f9b]/40",
                )}
              >
                <span className="font-semibold text-[#11113f]">Подаю самостоятельно</span>
                <span className="mt-1 block text-xs leading-relaxed text-[#6d6d7d]">Роспатент будет переписываться с заявителем.</span>
              </button>
              <button
                type="button"
                onClick={() => setUsesRepresentative(true)}
                className={cn(
                  "rounded-xl border p-4 text-left transition-colors",
                  usesRepresentative ? "border-[#0d9f9b] bg-[#eef9f8]" : "border-[#11113f]/10 bg-white hover:border-[#0d9f9b]/40",
                )}
              >
                <span className="font-semibold text-[#11113f]">Через представителя</span>
                <span className="mt-1 block text-xs leading-relaxed text-[#6d6d7d]">Он будет указан в заявлении и сможет вести переписку.</span>
              </button>
            </div>

            {usesRepresentative && (
              <div className="space-y-4 rounded-2xl border border-[#0d9f9b]/25 bg-[#f8fcfb] p-4 sm:p-5">
                <MarkedField label="ФИО представителя" mode="manual">
                  <Input value={representative.fullName} onChange={(event) => setRepresentative((old) => ({ ...old, fullName: event.target.value }))} placeholder="Иванов Иван Иванович" />
                </MarkedField>
                <div className="grid gap-4 sm:grid-cols-2">
                  <MarkedField label="Адрес для переписки" mode="manual">
                    <Input value={representative.address} onChange={(event) => setRepresentative((old) => ({ ...old, address: event.target.value }))} placeholder="Индекс, регион, город, улица, дом" />
                  </MarkedField>
                  <MarkedField label="Роль" mode="manual">
                    <Input value={representative.role} disabled={representative.isPatentAttorney} onChange={(event) => setRepresentative((old) => ({ ...old, role: event.target.value }))} placeholder="Например: юрист" />
                  </MarkedField>
                  <MarkedField label="E-mail" mode="manual">
                    <Input type="email" value={representative.email} onChange={(event) => setRepresentative((old) => ({ ...old, email: event.target.value }))} />
                  </MarkedField>
                  <MarkedField label="Телефон" mode="manual">
                    <Input value={representative.phone} onChange={(event) => setRepresentative((old) => ({ ...old, phone: event.target.value }))} />
                  </MarkedField>
                </div>

                <label className="flex cursor-pointer items-start gap-3 rounded-xl border border-[#11113f]/10 bg-white p-4">
                  <Checkbox
                    checked={representative.isPatentAttorney}
                    onCheckedChange={(checked) => setRepresentative((old) => ({ ...old, isPatentAttorney: checked === true }))}
                  />
                  <span>
                    <span className="text-sm font-semibold text-[#11113f]">Это патентный поверенный</span>
                    <span className="mt-1 block text-xs leading-relaxed text-[#6d6d7d]">Отметьте только если специалист зарегистрирован в государственном реестре патентных поверенных.</span>
                  </span>
                </label>
                {representative.isPatentAttorney && <MarkedField label="Регистрационный номер патентного поверенного" mode="manual"><Input value={representative.registrationNumber} onChange={(event) => setRepresentative((old) => ({ ...old, registrationNumber: event.target.value }))} placeholder="Номер из реестра" /></MarkedField>}

                <MarkedField label="На каком основании действует представитель" mode="manual">
                  <Select value={representative.authorityType} onValueChange={(value: "power_of_attorney" | "law" | "charter") => setRepresentative((old) => ({ ...old, authorityType: value }))}>
                    <SelectTrigger><SelectValue /></SelectTrigger>
                    <SelectContent>
                      <SelectItem value="power_of_attorney">По доверенности</SelectItem>
                      <SelectItem value="law">На основании закона</SelectItem>
                      <SelectItem value="charter">На основании устава</SelectItem>
                    </SelectContent>
                  </Select>
                </MarkedField>

                {representative.authorityType === "power_of_attorney" && (
                  <div className="space-y-3 rounded-xl border border-amber-200 bg-amber-50 p-4">
                    <MarkedField label="Номер и дата доверенности" mode="manual">
                      <Input value={representative.poaReference} onChange={(event) => setRepresentative((old) => ({ ...old, poaReference: event.target.value }))} placeholder="Например: № 12 от 28.08.2026" />
                    </MarkedField>
                    <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
                      <div>
                        <p className="text-sm font-semibold text-[#11113f]">Файл доверенности</p>
                        <p className="mt-1 text-xs text-[#6d6d7d]">{powerOfAttorneyDocument ? powerOfAttorneyDocument.original_filename : "Приложите документ — он войдёт в итоговый ZIP."}</p>
                      </div>
                      <Button type="button" variant="outline" disabled={powerOfAttorneyUploading} onClick={() => powerOfAttorneyInput.current?.click()} className="rounded-full bg-white">
                        {powerOfAttorneyUploading ? <Loader2 className="h-4 w-4 animate-spin" /> : <Upload className="h-4 w-4" />}
                        {powerOfAttorneyDocument ? "Заменить файл" : "Добавить доверенность"}
                      </Button>
                      <input ref={powerOfAttorneyInput} type="file" className="hidden" accept=".pdf,.docx,.png,.jpg,.jpeg" onChange={(event) => void uploadPowerOfAttorney(event.target.files?.[0])} />
                    </div>
                  </div>
                )}
              </div>
            )}
          </div>
        </FormGroup>}

        <FormGroup step={mode === "review" ? 4 : undefined} id="mark-data" title="О товарном знаке" hint="Проверьте обозначение, материалы и точный перечень товаров или услуг">
          <MarkedField label={<span className="inline-flex items-center gap-1">Вид знака <HelpTip text="Словесный знак защищает написанное название. Изобразительный — картинку без текста. Комбинированный — название и изображение вместе." /></span>} source={sourceFor("mark_type", Boolean(form.markType))}>
            <Select value={form.markType} onValueChange={(value) => set("markType", value)}><SelectTrigger><SelectValue /></SelectTrigger><SelectContent>{(Object.keys(MARK_TYPE_LABELS) as MarkType[]).map((type) => <SelectItem key={type} value={type}>{MARK_TYPE_LABELS[type]}</SelectItem>)}</SelectContent></Select>
          </MarkedField>
          <MarkedField label="Обозначение" source={sourceFor("mark_name", Boolean(form.markName))}><Input value={form.markName} onChange={(e) => set("markName", e.target.value)} /></MarkedField>
          {imageMark && (
            <div className="rounded-2xl border border-[#0d9f9b]/25 bg-[#eef9f8] p-4">
              <div className="flex items-start justify-between gap-3">
                <div>
                  <Label className="inline-flex items-center gap-1 text-sm font-semibold">
                    Изображение обозначения
                    <HelpTip text="Загрузите именно тот вариант логотипа или рисунка, который планируете регистрировать. Для комбинированного знака защищается сочетание изображения и слов." />
                  </Label>
                  <p className="mt-1 text-xs leading-relaxed text-[#6d6d7d]">PNG или JPEG. Мы проверим файл, покажем его и попробуем прочитать слова.</p>
                </div>
                <div className="flex flex-wrap items-center justify-end gap-2">
                  <span className="rounded-full bg-amber-100 px-2.5 py-1 text-[11px] font-bold text-amber-800">Обязательно</span>
                  <SourceBadge source={sourceFor("mark_image", Boolean(markImage))} />
                </div>
              </div>

              {markImage && previewUrl ? (
                <div className="mt-4 grid gap-4 sm:grid-cols-[150px_1fr]">
                  <div className="flex min-h-36 items-center justify-center rounded-xl border border-[#11113f]/10 bg-white p-3">
                    <img src={previewUrl} alt="Загруженное обозначение" className="max-h-32 max-w-full object-contain" />
                  </div>
                  <div className="min-w-0">
                    <p className="truncate font-semibold text-[#11113f]">{markImage.filename}</p>
                    <p className="mt-1 text-xs text-[#6d6d7d]">{markImage.width} × {markImage.height} px · {markImage.format} · {(markImage.file_size / 1024).toFixed(0)} КБ</p>
                    {markImage.dominant_colors.length > 0 && (
                      <div className="mt-3 flex items-center gap-2 text-xs text-[#6d6d7d]">
                        Основные цвета
                        {markImage.dominant_colors.map((color) => <span key={color} title={color} className="h-5 w-5 rounded-full border border-black/10" style={{ backgroundColor: color }} />)}
                      </div>
                    )}
                    <div className="mt-4 flex flex-wrap gap-2">
                      <label className="inline-flex cursor-pointer items-center gap-2 rounded-full border border-[#11113f]/15 bg-white px-4 py-2 text-xs font-semibold hover:bg-[#f8f7f4]">
                        <Upload className="h-4 w-4" /> Заменить
                        <input type="file" accept="image/png,image/jpeg" className="sr-only" onChange={(event) => void uploadMarkImage(event.target.files?.[0])} />
                      </label>
                      <button type="button" onClick={() => void removeMarkImage()} className="inline-flex items-center gap-2 rounded-full px-4 py-2 text-xs font-semibold text-red-700 hover:bg-red-50"><Trash2 className="h-4 w-4" /> Удалить</button>
                    </div>
                  </div>
                </div>
              ) : (
                <label className="mt-4 flex min-h-32 cursor-pointer flex-col items-center justify-center rounded-xl border border-dashed border-[#0d9f9b]/45 bg-white px-5 text-center hover:border-[#0d9f9b]">
                  {imageUploading ? <Loader2 className="h-7 w-7 animate-spin text-[#0d9f9b]" /> : <ImageIcon className="h-7 w-7 text-[#0d9f9b]" />}
                  <span className="mt-2 text-sm font-semibold text-[#11113f]">{imageUploading ? "Обрабатываем изображение…" : "Выбрать изображение"}</span>
                  <span className="mt-1 text-xs text-[#6d6d7d]">до 25 МБ</span>
                  <input disabled={imageUploading} type="file" accept="image/png,image/jpeg" className="sr-only" onChange={(event) => void uploadMarkImage(event.target.files?.[0])} />
                </label>
              )}

              {form.markType === "combined" && (
                <div className="mt-4">
                  <div className="flex flex-wrap items-center justify-between gap-2"><Label className="inline-flex items-center gap-1 text-sm font-semibold">Слова на логотипе <HelpTip text="Мы используем подтверждённые слова для поиска похожих названий. Исправьте ошибки распознавания и укажите все читаемые словесные элементы." /></Label><SourceBadge source={sourceFor("mark_text", Boolean(form.markText))} /></div>
                  <Input className="mt-2 bg-white" value={form.markText} onChange={(event) => set("markText", event.target.value)} placeholder="Например: Регистр" />
                  <p className="mt-2 text-xs leading-relaxed text-[#6d6d7d]">{markImage?.recognized_text ? "Текст предложен OCR — обязательно сверьте его с картинкой." : "Если на изображении есть слова, введите их вручную."}</p>
                </div>
              )}

              <div className="mt-4 rounded-xl bg-amber-50 px-3 py-2 text-xs leading-relaxed text-amber-900">
                <strong>Что проверяется:</strong> система сравнит и слова на логотипе, и изображение с доступными карточками реестра.
              </div>
            </div>
          )}
          {soundMark && (
            <div className="rounded-2xl border border-[#0d9f9b]/25 bg-[#eef9f8] p-4">
              <div className="flex flex-wrap items-center justify-between gap-2"><Label className="inline-flex items-center gap-1 text-sm font-semibold">Аудиозапись обозначения <HelpTip text="Загрузите запись именно того звука, который хотите зарегистрировать. Рекомендуемый Роспатентом формат — MP3; поддерживается и WAV." /></Label><SourceBadge source={sourceFor("mark_audio", Boolean(markAudio))} /></div>
              <p className="mt-1 text-xs leading-relaxed text-[#6d6d7d]">MP3 или WAV, до 25 МБ. После загрузки отдельно проверьте описание звучания.</p>
              {markAudio ? (
                <div className="mt-4 flex flex-wrap items-center justify-between gap-3 rounded-xl bg-white p-4">
                  <div><p className="font-semibold text-[#11113f]">{markAudio.original_filename}</p><p className="mt-1 text-xs text-[#6d6d7d]">Аудиозапись сохранена · {(markAudio.file_size / 1024 / 1024).toFixed(1)} МБ</p></div>
                  <label className="cursor-pointer rounded-full border border-[#11113f]/15 px-4 py-2 text-xs font-semibold">Заменить<input type="file" accept="audio/mpeg,audio/wav,.mp3,.wav" className="sr-only" onChange={(event) => void uploadMarkAudio(event.target.files?.[0])} /></label>
                </div>
              ) : (
                <label className="mt-4 flex min-h-28 cursor-pointer flex-col items-center justify-center rounded-xl border border-dashed border-[#0d9f9b]/45 bg-white px-5 text-center">
                  {audioUploading ? <Loader2 className="h-7 w-7 animate-spin text-[#0d9f9b]" /> : <Upload className="h-7 w-7 text-[#0d9f9b]" />}
                  <span className="mt-2 text-sm font-semibold">{audioUploading ? "Загружаем…" : "Выбрать MP3 или WAV"}</span>
                  <input disabled={audioUploading} type="file" accept="audio/mpeg,audio/wav,.mp3,.wav" className="sr-only" onChange={(event) => void uploadMarkAudio(event.target.files?.[0])} />
                </label>
              )}
            </div>
          )}
          {mode === "review" && <><MarkedField label={<span className="inline-flex items-center gap-1">Что вы продаёте или какие услуги оказываете <HelpTip text="Перечислите всё, что вы продаёте или делаете под этим названием. По этому описанию система подберёт классы МКТУ — группы товаров и услуг, для которых будет действовать защита знака." /></span>} source={sourceFor("goods_services", Boolean(activityDescription))}>
            <Textarea
              rows={3}
              value={activityDescription}
              onChange={(event) => setForm((old) => ({
                ...old,
                business: event.target.value,
                goods: event.target.value,
              }))}
              placeholder="Например: ремонт квартир, пошив одежды или доставка еды"
            />
          </MarkedField>
          <details open className="rounded-xl border border-[#11113f]/10 bg-white p-4">
            <summary className="cursor-pointer font-semibold text-[#11113f]">Описание и цвета для заявления</summary>
            <div className="mt-3 flex flex-wrap items-center justify-between gap-3"><p className="max-w-2xl text-xs leading-relaxed text-[#6d6d7d]">Система подготовит описание, основные цвета, написание латиницей и перевод. Проверьте результат перед сохранением.</p><Button type="button" variant="outline" size="sm" disabled={autoFilling} onClick={() => void generateAllDetails()}>{autoFilling ? <Loader2 className="h-4 w-4 animate-spin" /> : <Sparkles className="h-4 w-4" />} Подготовить сведения</Button></div>
            <div className="mt-4 space-y-4">
              <MarkedField label="Описание обозначения" source={sourceFor("mark_description", Boolean(form.description))}><Textarea rows={6} value={form.description} onChange={(e) => set("description", e.target.value)} placeholder="Нажмите «Подготовить сведения»" /></MarkedField>
              <MarkedField label="Основные цвета обозначения" source={sourceFor("colors_claimed", Boolean(form.colors))}><Input value={form.colors} onChange={(e) => set("colors", e.target.value)} placeholder="Определятся по изображению" /></MarkedField>
              {foreignWording && <div className="grid gap-4 sm:grid-cols-2">
                <MarkedField label="Написание латиницей" source={sourceFor("transliteration", Boolean(form.transliteration))}><Input value={form.transliteration} onChange={(e) => set("transliteration", e.target.value)} placeholder="Определится автоматически" /></MarkedField>
                <MarkedField label="Перевод названия" source={sourceFor("translation", Boolean(form.translation))}><Input value={form.translation} onChange={(e) => set("translation", e.target.value)} placeholder="Например: Friendly Neighbor" /></MarkedField>
              </div>}
            </div>
          </details></>}
        </FormGroup>
      </div>
      {mode === "review" && appId && onAnalysis && (
        <ClientCheck
          appId={appId}
          onAnalysis={onAnalysis}
          beforeAction={save}
          dataConfirmed={dataConfirmed}
          confirmingData={confirmingData}
          onConfirmData={confirmReviewedData}
          onDataChange={() => setDataConfirmed(false)}
        />
      )}
      {mode === "upload" && <div className="mt-8 flex justify-end"><Button disabled={saving} onClick={() => void save()} className="rounded-full bg-[#0d9f9b] px-7 hover:bg-[#078984]">{saving && <Loader2 className="h-4 w-4 animate-spin" />} Перейти к проверке данных <ChevronRight className="h-4 w-4" /></Button></div>}
    </ClientPanel>
  );
}

function FormGroup({ id, step, title, hint, children }: { id?: string; step?: number; title: React.ReactNode; hint: string; children: React.ReactNode }) {
  return <section id={id} className="scroll-mt-28 rounded-[1.3rem] bg-[#f8f7f4] p-5 sm:p-6">
    {step && <div className="mb-4 flex items-center gap-3"><span className="flex h-8 w-8 shrink-0 items-center justify-center rounded-full bg-[#11113f] text-sm font-bold text-white">{step}</span><p className="text-xs font-bold uppercase tracking-[0.14em] text-[#0d9f9b]">Шаг {step} из 4</p></div>}
    <h3 className="text-xl font-semibold">{title}</h3><p className="mt-1 text-sm text-[#6d6d7d]">{hint}</p><div className="mt-6 space-y-5">{children}</div>
  </section>;
}

function SourceBadge({ source }: { source: FieldSourceDto }) {
  const colors: Record<FieldSourceKind, string> = {
    document: "bg-emerald-100 text-emerald-800",
    system: "bg-sky-100 text-sky-800",
    user: source.filled ? "bg-[#ececf5] text-[#34345f]" : "bg-amber-100 text-amber-800",
    rospatent: "bg-violet-100 text-violet-800",
    profile: "bg-teal-100 text-teal-800",
  };
  return <span className="inline-flex items-center gap-1.5">
    <span className={cn("rounded-full px-2.5 py-1 text-[11px] font-bold", colors[source.source])}>{source.label}</span>
    <HelpTip text={source.detail} />
  </span>;
}

function MarkedField({ label, source, mode, children }: { label: React.ReactNode; source?: FieldSourceDto; mode?: "manual" | "document"; children: React.ReactNode }) {
  const resolved = source || {
    code: "legacy",
    source: mode === "document" ? "document" as const : "user" as const,
    label: mode === "document" ? "Из документа — проверьте" : "Заполнить вручную",
    detail: mode === "document" ? "Значение извлечено из документа. Сверьте его с оригиналом." : "Укажите значение самостоятельно.",
    filled: mode === "document",
    verification_required: mode === "document",
  };
  return <div><div className="mb-2 flex flex-wrap items-center justify-between gap-2"><Label className="text-sm font-semibold">{label}</Label><SourceBadge source={resolved} /></div>{children}</div>;
}

function ClientCheck({ appId, onAnalysis, beforeAction, dataConfirmed, confirmingData, onConfirmData, onDataChange }: { appId: number; onAnalysis: () => void; beforeAction: () => Promise<boolean>; dataConfirmed: boolean; confirmingData: boolean; onConfirmData: () => Promise<void>; onDataChange: () => void }) {
  const { toast } = useToast();
  const initialLoadStarted = useRef(false);
  const [classes, setClasses] = useState<ClassSuggestion[]>([]);
  const [loading, setLoading] = useState(true);
  const [running, setRunning] = useState(false);
  const [preparing, setPreparing] = useState(false);
  const [decidingClassId, setDecidingClassId] = useState<number | null>(null);
  const [recalculatingClasses, setRecalculatingClasses] = useState(false);
  const [editingClassIds, setEditingClassIds] = useState<Set<number>>(new Set());
  const [narrowingClassId, setNarrowingClassId] = useState<number | null>(null);
  const [narrowingPreviews, setNarrowingPreviews] = useState<Record<number, ClassNarrowingPreview>>({});
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

  const load = async (autoSuggest = true) => {
    setLoading(true);
    const classData = await api.get<{ suggestions: ClassSuggestion[] }>(`/applications/${appId}/classes`).catch(() => ({ suggestions: [] }));
    if (autoSuggest && classData.suggestions.length === 0) {
      await api.post(`/applications/${appId}/nice-classes/suggest`).catch(() => undefined);
      return load(false);
    }
    setClasses(classData.suggestions);
    setLoading(false);
  };
  useEffect(() => {
    if (initialLoadStarted.current) return;
    initialLoadStarted.current = true;
    void load();
  }, [appId]);

  const decide = async (item: ClassSuggestion, approved: boolean) => {
    setDecidingClassId(item.id);
    const payload: { suggestion_id: number; approved: boolean; class_description?: string | null } = { suggestion_id: item.id, approved };
    if (editingClassIds.has(item.id)) payload.class_description = item.class_description;
    try { await api.put(`/applications/${appId}/classes/${item.id}/approve`, payload); setEditingClassIds((current) => { const next = new Set(current); next.delete(item.id); return next; }); onDataChange(); await load(); }
    catch (error) { toast({ title: "Не удалось сохранить выбор", description: messageOf(error, "Попробуйте ещё раз"), variant: "destructive" }); }
    finally { setDecidingClassId(null); }
  };

  const previewNarrowing = async (item: ClassSuggestion) => {
    setNarrowingClassId(item.id);
    try {
      const preview = await api.post<ClassNarrowingPreview>(
        `/applications/${appId}/classes/${item.id}/narrow`,
        {},
      );
      setNarrowingPreviews((current) => ({ ...current, [item.id]: preview }));
    } catch (error) {
      toast({
        title: "Не удалось сузить перечень",
        description: messageOf(error, "Полный перечень не изменён. Попробуйте ещё раз."),
        variant: "destructive",
      });
    } finally {
      setNarrowingClassId(null);
    }
  };

  const applyNarrowing = async (item: ClassSuggestion, preview: ClassNarrowingPreview) => {
    setNarrowingClassId(item.id);
    try {
      await api.post(
        `/applications/${appId}/classes/${item.id}/narrow/apply`,
        { selected_items: preview.selected_items },
      );
      setNarrowingPreviews((current) => {
        const next = { ...current };
        delete next[item.id];
        return next;
      });
      onDataChange();
      await load();
      toast({
        title: "Перечень сокращён",
        description: `Оставлено ${preview.selected_count} из ${preview.source_count} официальных позиций. Проверьте список и подтвердите класс.`,
      });
    } catch (error) {
      toast({
        title: "Не удалось применить перечень",
        description: messageOf(error, "Исходный перечень не изменён."),
        variant: "destructive",
      });
    } finally {
      setNarrowingClassId(null);
    }
  };

  const recalculateClasses = async () => {
    setRecalculatingClasses(true);
    if (!(await beforeAction())) { setRecalculatingClasses(false); return; }
    try {
      const result = await api.post<{
        status: string;
        suggestions?: unknown[];
        reason?: string;
      }>(`/applications/${appId}/nice-classes/suggest?replace_all=true`);
      onDataChange();
      await load(false);
      toast({
        title: result.status === "ok" ? "Классы подобраны моделью" : "Использован справочник МКТУ",
        description: result.status === "ok"
          ? `Прежний список заменён. По актуальным данным предложено классов: ${result.suggestions?.length || 0}.`
          : `Модель не дала надёжного ответа. Система применила проверенные правила и официальный справочник. ${result.reason || ""}`.trim(),
      });
    } catch (error) {
      toast({
        title: "Не удалось подобрать классы заново",
        description: messageOf(error, "Проверьте описание товаров и услуг и попробуйте ещё раз"),
        variant: "destructive",
      });
    } finally {
      setRecalculatingClasses(false);
    }
  };

  const run = async () => {
    setPreparing(true);
    if (!(await beforeAction())) { setPreparing(false); return; }
    setPreparing(false);
    setRunning(true);
    try {
      await api.post<AnalysisJob>(`/applications/${appId}/full-analysis/jobs`, { retry_incomplete_only: false });
      onAnalysis();
      toast({ title: "Проверка началась", description: "Открылся экран с ходом анализа. Его можно безопасно покинуть и вернуться позже." });
    }
    catch (error) { toast({ title: "Проверка не выполнена", description: messageOf(error, "Попробуйте ещё раз"), variant: "destructive" }); }
    finally { setRunning(false); }
  };

  if (loading) return <section id="class-confirmation" className="mt-6 scroll-mt-28 rounded-[1.3rem] bg-[#f8f7f4] p-5 sm:p-6">
    <div className="mb-4 flex items-center gap-3"><span className="flex h-8 w-8 shrink-0 items-center justify-center rounded-full bg-[#11113f] text-sm font-bold text-white">4</span><p className="text-xs font-bold uppercase tracking-[0.14em] text-[#0d9f9b]">Шаг 4 из 4 · последнее перед анализом</p></div>
    <div className="flex min-h-40 items-center justify-center rounded-[1.2rem] border border-[#11113f]/10 bg-white text-[#6d6d7d]"><Loader2 className="mr-2 h-5 w-5 animate-spin" /> Загружаем предложенные классы…</div>
  </section>;

  const approved = classes.filter((item) => item.approved === true).length;
  const hasPendingClasses = classes.some((item) => item.approved === null);
  const usedCatalogFallback = classes.some((item) => item.rationale?.startsWith("Справочник МКТУ:"));

  return (
    <section id="class-confirmation" className="mt-6 scroll-mt-28 rounded-[1.3rem] bg-[#f8f7f4] p-5 sm:p-6">
      <div className="mb-4 flex items-center gap-3"><span className="flex h-8 w-8 shrink-0 items-center justify-center rounded-full bg-[#11113f] text-sm font-bold text-white">4</span><p className="text-xs font-bold uppercase tracking-[0.14em] text-[#0d9f9b]">Шаг 4 из 4 · последнее перед анализом</p></div>
      <h3 className="mt-2 text-xl font-semibold text-[#11113f]">Проверьте классы товаров и услуг</h3>
      <p className="mt-2 text-sm leading-relaxed text-[#6d6d7d]">Класс показывает, для каких именно товаров или услуг будет защищён знак. Отметьте каждый предложенный вариант.</p>
        <section className="mt-5 rounded-[1.3rem] border border-[#0d9f9b]/20 bg-white p-4 sm:p-5">
          <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
            <h4 className="inline-flex items-center gap-1 font-semibold">Предложенные классы <HelpTip text="МКТУ — международный справочник из 45 классов. Классы 1–34 относятся к товарам, 35–45 — к услугам. Правовая охрана действует в отношении товаров и услуг, перечисленных в заявке, поэтому важно правильно выбрать направления работы." /></h4>
            <div className="flex flex-wrap items-center gap-2">
              <Badge variant="outline">Выбрано: {approved}</Badge>
              <Button
                type="button"
                size="sm"
                variant="outline"
                disabled={recalculatingClasses}
                onClick={() => void recalculateClasses()}
                className="rounded-full"
                data-testid="button-recalculate-classes"
              >
                {recalculatingClasses ? <Loader2 className="h-4 w-4 animate-spin" /> : <RefreshCw className="h-4 w-4" />}
                {recalculatingClasses ? "Подбираем…" : "Подобрать заново"}
              </Button>
            </div>
          </div>
          <p className="mt-2 text-sm leading-relaxed text-[#6d6d7d]">Система группирует вашу деятельность по международному справочнику МКТУ. Подтвердите только те направления, которыми вы действительно занимаетесь или планируете заниматься.</p>
          <p className="mt-2 rounded-lg bg-[#eef9f8] px-3 py-2 text-xs leading-relaxed text-[#315c5a]">По умолчанию в заявку попадёт полный официальный перечень товаров или услуг выбранного класса. Если он не помещается в бланк, система автоматически вынесет его в приложение. Сокращайте перечень только осознанно: удалённые позиции не будут охраняться.</p>
          <p className="mt-2 rounded-lg bg-[#f8f7f4] px-3 py-2 text-xs leading-relaxed text-[#5f6072]">
            Изменили документы, описание бизнеса или перечень товаров? Нажмите «Подобрать заново». Прежние классы будут удалены, а список сформируется заново по актуальным данным.
          </p>
          {usedCatalogFallback && <div className="mt-3 flex items-start gap-2 rounded-xl border border-amber-200 bg-amber-50 p-3 text-sm leading-relaxed text-amber-900"><AlertCircle className="mt-0.5 h-4 w-4 shrink-0" /><p><span className="font-semibold">Языковая модель не дала надёжного результата.</span> Эти варианты подобраны по официальному справочнику и встроенным правилам. Обязательно проверьте их перед анализом.</p></div>}
          <div className="mt-5 space-y-3">
            {classes.length === 0 ? (
              <div className="rounded-xl bg-[#f8f7f4] p-4 text-sm text-[#6d6d7d]">Предложений пока нет. Нажмите «Подобрать заново» — система предложит классы по вашему описанию услуг.</div>
            ) : classes.map((item) => {
              const description = item.class_description || "";
              const itemCount = description ? description.split(";").filter((part) => part.trim()).length : 0;
              const isEditing = editingClassIds.has(item.id);
              const isFullList = description.length > 700 || itemCount > 12;
              const narrowingPreview = narrowingPreviews[item.id];
              const isNarrowing = narrowingClassId === item.id;
              return (
              <div key={item.id} className={cn("rounded-xl border p-4", item.approved === true ? "border-emerald-300 bg-emerald-50" : item.approved === false ? "border-[#11113f]/10 bg-[#f8f7f4] opacity-70" : "border-amber-200 bg-amber-50")}>
                <div className="flex flex-col gap-4">
                  <div>
                    <p className="font-semibold">Что будет защищено в классе {item.class_number}</p>
                    <p className="mt-1 text-xs leading-relaxed text-[#6d6d7d]">Охрана будет действовать только для позиций из подтверждённого перечня.</p>
                    {narrowingPreview ? <div className="mt-3 rounded-xl border-2 border-[#0d9f9b]/35 bg-white p-4 shadow-sm">
                      <div className="flex items-start gap-3">
                        <span className="mt-0.5 flex h-8 w-8 shrink-0 items-center justify-center rounded-full bg-[#0d9f9b]/10 text-[#0b7774]"><Sparkles className="h-4 w-4" /></span>
                        <div>
                          <p className="font-semibold text-[#11113f]">Модель предлагает оставить {narrowingPreview.selected_count} из {narrowingPreview.source_count} позиций</p>
                          <p className="mt-1 text-xs leading-relaxed text-[#5f6072]">Это предварительный подбор по описанию вашей деятельности. Проверьте его: после применения удалённые позиции не войдут в заявку.</p>
                        </div>
                      </div>
                      {narrowingPreview.rationale && <p className="mt-3 rounded-lg bg-[#edf9f8] px-3 py-2 text-xs leading-relaxed text-[#315f5d]"><span className="font-semibold">Почему выбраны эти позиции:</span> {narrowingPreview.rationale}</p>}
                      <details open className="mt-3 text-xs text-[#4f5063]"><summary className="cursor-pointer font-semibold text-[#0d8f8b]">Проверить предложенный перечень</summary><div className="mt-2 max-h-52 overflow-y-auto rounded-lg bg-[#f8f7f4] p-3 leading-relaxed">{narrowingPreview.selected_items.map((entry) => <p key={entry} className="border-b border-[#11113f]/5 py-1.5 last:border-0">{entry}</p>)}</div></details>
                      {narrowingPreview.assumptions.length > 0 && <div className="mt-3 rounded-lg border border-amber-200 bg-amber-50 px-3 py-2 text-xs leading-relaxed text-amber-900"><span className="font-semibold">Что модель предположила:</span> {narrowingPreview.assumptions.join("; ")}</div>}
                      <div className="mt-4 flex flex-wrap gap-2">
                        <Button type="button" size="sm" className="rounded-full" disabled={isNarrowing} onClick={() => void applyNarrowing(item, narrowingPreview)}>{isNarrowing ? <Loader2 className="h-4 w-4 animate-spin" /> : <Check className="h-4 w-4" />} {isNarrowing ? "Применяем…" : "Применить сокращение"}</Button>
                        <Button type="button" size="sm" variant="outline" className="rounded-full" disabled={isNarrowing} onClick={() => setNarrowingPreviews((current) => { const next = { ...current }; delete next[item.id]; return next; })}>Оставить полный перечень</Button>
                      </div>
                    </div> : isEditing ? <div className="mt-3">
                      <div className="mb-2 rounded-lg border border-amber-200 bg-amber-50 px-3 py-2 text-xs leading-relaxed text-amber-900">Вы редактируете официальный перечень. Всё удалённое не войдёт в заявку и не будет охраняться.</div>
                      <Textarea
                        className="max-h-80 min-h-40 bg-white"
                        value={description}
                        onChange={(event) => setClasses((current) => current.map((entry) => entry.id === item.id ? { ...entry, class_description: event.target.value } : entry))}
                        placeholder="Например: установка, обслуживание и ремонт компьютеров"
                      />
                      <Button type="button" size="sm" variant="ghost" className="mt-2 rounded-full" onClick={() => setEditingClassIds((current) => { const next = new Set(current); next.delete(item.id); return next; })}>Отменить редактирование</Button>
                    </div> : isFullList ? <div className="mt-3 rounded-xl border border-[#0d9f9b]/20 bg-white p-3">
                      <p className="text-sm font-semibold text-[#0b7774]">Полный перечень класса · около {itemCount} позиций</p>
                      <p className="mt-1 text-xs leading-relaxed text-[#6d6d7d]">Он будет вынесен в приложение к заявке автоматически.</p>
                      <details className="mt-2 text-xs text-[#4f5063]"><summary className="cursor-pointer font-semibold text-[#0d8f8b]">Посмотреть перечень</summary><div className="mt-2 max-h-52 overflow-y-auto whitespace-pre-wrap rounded-lg bg-[#f8f7f4] p-3 leading-relaxed">{description}</div></details>
                      <Button type="button" size="sm" variant="outline" className="mt-3 rounded-full" disabled={isNarrowing} onClick={() => void previewNarrowing(item)}>{isNarrowing ? <Loader2 className="h-4 w-4 animate-spin" /> : <Sparkles className="h-4 w-4" />} {isNarrowing ? "Подбираем подходящие…" : "Сузить перечень с моделью"}</Button>
                    </div> : <div className="mt-3 rounded-xl border border-[#11113f]/10 bg-white p-3">
                      <p className="whitespace-pre-wrap text-sm leading-relaxed text-[#34354b]">{description || "Перечень пока не заполнен"}</p>
                      <div className="mt-3 flex flex-wrap gap-2"><Button type="button" size="sm" variant="outline" className="rounded-full" disabled={isNarrowing} onClick={() => void previewNarrowing(item)}>{isNarrowing ? <Loader2 className="h-4 w-4 animate-spin" /> : <Sparkles className="h-4 w-4" />} {isNarrowing ? "Подбираем…" : "Подобрать моделью"}</Button><Button type="button" size="sm" variant="ghost" className="rounded-full" onClick={() => setEditingClassIds((current) => new Set(current).add(item.id))}>Уточнить вручную</Button></div>
                    </div>}
                    {item.rationale && <p className="mt-2 rounded-lg bg-white/70 px-3 py-2 text-xs leading-relaxed text-[#55556f]"><span className="font-semibold text-[#11113f]">Почему предложен:</span> {item.rationale}</p>}
                  </div>
                  <div className="flex flex-wrap gap-2">
                    <Button disabled={decidingClassId !== null} size="sm" variant={item.approved === true ? "default" : "outline"} className="rounded-full" onClick={() => void decide(item, true)}>{decidingClassId === item.id ? <Loader2 className="h-4 w-4 animate-spin" /> : <Check className="h-4 w-4" />} {decidingClassId === item.id ? "Сохраняем…" : "Подходит"}</Button>
                    <Button disabled={decidingClassId !== null} size="sm" variant="ghost" className="rounded-full" onClick={() => void decide(item, false)}>{decidingClassId === item.id ? <Loader2 className="h-4 w-4 animate-spin" /> : null} {decidingClassId === item.id ? "Сохраняем…" : "Не подходит"}</Button>
                  </div>
                </div>
              </div>
            );})}
          </div>
        </section>
      <div className="mt-7 rounded-[1.2rem] bg-[#11113f] p-5 text-white">
        <div className="flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between sm:gap-6"><div><p className="font-semibold">{preparing ? "Сохраняем введённые данные" : running ? phases[phase] : hasPendingClasses ? "Сначала подтвердите классы" : approved === 0 ? "Выберите хотя бы один класс" : !dataConfirmed ? "Подтвердите проверенные сведения" : "Всё готово к анализу"}</p><p className="mt-1 text-sm text-white/65">{preparing ? "После сохранения автоматически откроется следующий экран." : running ? "Вы уже можете следить за проверкой на следующем экране." : hasPendingClasses ? "Для каждого предложенного класса нажмите «Подходит» или «Не подходит»." : !dataConfirmed ? "Подтвердите, что сверили реквизиты, обозначение и перечень товаров или услуг." : "Поиск проводится прежде всего в выбранных классах товаров и услуг."}</p>{(preparing || running) && <div className="mt-3 flex gap-1.5">{phases.map((_, index) => <span key={index} className={cn("h-1.5 w-10 rounded-full", !preparing && index <= phase ? "bg-[#43c7c2]" : "bg-white/15")} />)}</div>}</div><Button disabled={preparing || running || hasPendingClasses || approved === 0 || !dataConfirmed} onClick={() => void run()} className="rounded-full bg-[#12aaa5] px-6 hover:bg-[#0d918d]">{preparing || running ? <Loader2 className="h-4 w-4 animate-spin" /> : <Play className="h-4 w-4" />} {preparing ? "Сохраняем…" : running ? "Запускаем анализ…" : "Продолжить к анализу"}</Button></div>
        {!hasPendingClasses && approved > 0 && !dataConfirmed && <button type="button" disabled={confirmingData} onClick={() => void onConfirmData()} className="mt-4 flex w-full items-start gap-3 rounded-xl border border-white/15 bg-white/10 p-4 text-left hover:bg-white/15 disabled:opacity-60"><span className="mt-0.5 flex h-5 w-5 shrink-0 items-center justify-center rounded border border-white/60">{confirmingData ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : null}</span><span><span className="block text-sm font-semibold">Я проверил сведения и подтверждаю их</span><span className="mt-1 block text-xs leading-relaxed text-white/60">Автоматически заполненные значения сверены с документами, а товары и услуги описаны верно.</span></span></button>}
        {dataConfirmed && <p className="mt-4 flex items-center gap-2 text-sm font-semibold text-[#79ded9]"><CheckCircle2 className="h-4 w-4" /> Сведения подтверждены</p>}
      </div>
    </section>
  );
}

function ClientResult({ application, appId, analysisPending, onAnalysisComplete, onReview, onApplication, onEditData }: { application: Application; appId: number; analysisPending: boolean; onAnalysisComplete: () => void; onReview: () => void; onApplication: () => void; onEditData: () => void }) {
  const { toast } = useToast();
  const [report, setReport] = useState<RiskReport | null>(null);
  const [memo, setMemo] = useState<Recommendation | null>(null);
  const [classes, setClasses] = useState<ClassSuggestion[]>([]);
  const [loading, setLoading] = useState(true);
  const [running, setRunning] = useState(false);
  const [analysisJob, setAnalysisJob] = useState<AnalysisJob | null>(null);

  const load = async () => {
    setLoading(true);
    const [risk, recommendation, classData] = await Promise.all([
      api.get<RiskReport>(`/applications/${appId}/risk-report`).catch(() => null),
      api.get<Recommendation>(`/applications/${appId}/recommendation`).catch(() => null),
      api.get<{ suggestions: ClassSuggestion[] }>(`/applications/${appId}/classes`).catch(() => ({ suggestions: [] })),
    ]);
    setReport(risk); setMemo(recommendation); setClasses(classData.suggestions); setLoading(false);
  };
  const activeJob = Boolean(analysisJob && ["queued", "running", "retrying"].includes(analysisJob.status));

  useEffect(() => {
    let cancelled = false;
    const bootstrap = async () => {
      const latest = await api.get<AnalysisJob>(`/applications/${appId}/full-analysis/jobs/latest`).catch(() => null);
      if (cancelled) return;
      setAnalysisJob(latest);
      if (!latest || !["queued", "running", "retrying"].includes(latest.status)) {
        await load();
        if (latest) onAnalysisComplete();
      } else {
        setLoading(false);
      }
    };
    void bootstrap();
    return () => { cancelled = true; };
  }, [appId, analysisPending]);

  useEffect(() => {
    if (!activeJob) return;
    let cancelled = false;
    const poll = async () => {
      const latest = await api.get<AnalysisJob>(`/applications/${appId}/full-analysis/jobs/latest`).catch(() => null);
      if (cancelled || !latest) return;
      setAnalysisJob(latest);
      if (!["queued", "running", "retrying"].includes(latest.status)) {
        setRunning(false);
        await load();
        onAnalysisComplete();
        if (latest.status === "failed") {
          toast({ title: "Не удалось завершить проверку", description: "Готовые результаты сохранены. Можно повторить незавершённую часть.", variant: "destructive" });
        }
      }
    };
    const timer = window.setInterval(() => void poll(), 1500);
    void poll();
    return () => { cancelled = true; window.clearInterval(timer); };
  }, [appId, activeJob]);

  const rerun = async () => {
    setRunning(true);
    try {
      const job = await api.post<AnalysisJob>(`/applications/${appId}/full-analysis/jobs`, { retry_incomplete_only: true });
      setAnalysisJob(job);
      setLoading(false);
    } catch (error) {
      setRunning(false);
      toast({ title: "Не удалось обновить результат", description: messageOf(error, "Попробуйте позже"), variant: "destructive" });
    }
  };
  const findings = useMemo(() => Object.values(report?.sections || {}).flatMap((section) => section?.findings || []), [report]);
  const risk = report?.overall_risk;
  const incomplete = report?.is_complete === false;
  const relativeSection = report?.sections?.relative_grounds;
  const absoluteSection = report?.sections?.absolute_grounds;
  const latestRelativeAttempt = report?.latest_attempts?.relative_grounds;
  const latestAbsoluteAttempt = report?.latest_attempts?.absolute_grounds;
  const lastCompletedRelativeSection = report?.last_completed_sections?.relative_grounds;
  const registrySearchSkipped = Boolean(
    relativeSection?.provenance?.verification?.skipped
    && relativeSection.provenance.verification.blocked_by === "absolute_grounds"
  );
  const registryConnectionFailed = Boolean(
    !registrySearchSkipped
    &&
    latestRelativeAttempt?.is_inconclusive
    && ((latestRelativeAttempt.provenance?.verification?.search_errors?.length || 0) > 0
      || (latestRelativeAttempt.provenance?.verification?.records_examined || 0) === 0)
  );
  const llmConnectionFailed = Boolean(
    latestAbsoluteAttempt?.is_inconclusive
    && (latestAbsoluteAttempt.missing_data || []).some((item) => item.toLocaleLowerCase("ru-RU").includes("ответ языковой модели"))
  );
  const externalServicesUnavailable = registryConnectionFailed || llmConnectionFailed;
  const effectiveRelativeSection = registrySearchSkipped
    ? relativeSection
    : relativeSection && !relativeSection.is_inconclusive
    ? relativeSection
    : lastCompletedRelativeSection;
  const registryResultIsPrevious = Boolean(
    !registrySearchSkipped && report?.refresh_warnings?.relative_grounds && lastCompletedRelativeSection
  );
  const retryAvailable = incomplete || registryResultIsPrevious;
  const registryFindings = effectiveRelativeSection?.findings || [];
  const registrySearchComplete = Boolean(
    effectiveRelativeSection
    && !effectiveRelativeSection.is_inconclusive
    && !registrySearchSkipped
  );
  const absoluteCheckIncomplete = Boolean(absoluteSection?.is_inconclusive);
  const unfinishedCheckTitle = absoluteCheckIncomplete
    ? "Что ещё нужно проверить: само обозначение"
    : !registrySearchComplete
      ? "Что ещё нужно проверить: похожие знаки"
      : "Что ещё нужно проверить";
  const allAdverseFindings = findings.filter((item) => ["medium", "high", "critical"].includes(item.level || ""));
  const rawAdverseFindings = allAdverseFindings.filter((item) => {
    const normalized = item.explanation.toLocaleLowerCase("ru-RU");
    if (
      application.markType === "combined"
      && ["misleading", "deceptive"].includes(item.category || "")
      && /(стиральн|холодильник|компьютер|инструмент)/.test(normalized)
      && /(ремонт|обслуживан|установк)/.test(normalized)
    ) {
      // Изображение предмета оказываемой услуги само по себе не сообщает
      // ложных сведений и не является основанием пугать клиента отказом.
      return false;
    }
    if (item.category !== "descriptive") return true;
    return ![
      "может восприниматься",
      "может указывать",
      "может ассоциироваться",
      "по-соседски",
      "состоит из общеупотребительных слов",
    ].some((phrase) => normalized.includes(phrase));
  });
  const adverseFindings = rawAdverseFindings.filter((item) => {
    if (!item.verification?.image_comparison || !item.verification.similarity) return true;
    const similarity = item.verification.similarity;
    // Грубая оценка картинки показывается юристу как подсказка, но не должна
    // пугать клиента, если слова, звучание и смысл обозначений различаются.
    return Math.max(similarity.phonetic || 0, similarity.visual || 0, similarity.semantic || 0) >= 0.5;
  });
  const onlyRoughImageRisks = rawAdverseFindings.length > 0 && adverseFindings.length === 0;
  const onlySpeculativeDescriptiveRisks = allAdverseFindings.length > 0 && rawAdverseFindings.length === 0;
  const displayedRisk = onlyRoughImageRisks || onlySpeculativeDescriptiveRisks
    ? (incomplete ? null : "low")
    : risk;
  // Уже установленный высокий риск важнее технической незавершённости
  // другой части проверки. Иначе экран одновременно советовал не подавать
  // знак, но прятал основание под заголовком «проверку нужно завершить».
  const presentation = displayedRisk ? {
    low: { title: "Можно продолжать", tone: "border-emerald-200 bg-emerald-50", icon: ShieldCheck, color: "text-emerald-700" },
    medium: { title: "Продолжайте с осторожностью", tone: "border-amber-200 bg-amber-50", icon: ShieldAlert, color: "text-amber-700" },
    high: { title: "Высокий риск отказа", tone: "border-orange-200 bg-orange-50", icon: ShieldAlert, color: "text-orange-700" },
    critical: { title: "Очень высокий риск отказа", tone: "border-red-200 bg-red-50", icon: AlertCircle, color: "text-red-700" },
  }[displayedRisk] : incomplete
    ? { title: externalServicesUnavailable ? "Проверка выполнена частично" : registrySearchComplete ? "По реестру явных препятствий не найдено" : "Проверку нужно завершить", tone: "border-amber-200 bg-amber-50", icon: ShieldAlert, color: "text-amber-700" }
    : null;

  if (analysisPending || activeJob) return (
    <ClientPanel title="Проверяем товарный знак" description="Можно ничего не нажимать — экран обновится автоматически. Проверка продолжится, даже если вы перейдёте в другой раздел.">
      <div className="rounded-[1.3rem] border border-[#0d9f9b]/25 bg-[#eef9f8] p-6 sm:p-8">
        <div className="flex items-start gap-4">
          <span className="flex h-12 w-12 shrink-0 items-center justify-center rounded-full bg-white text-[#0d9f9b]"><Loader2 className="h-6 w-6 animate-spin" /></span>
          <div>
            <h3 className="text-xl font-semibold text-[#11113f]">{analysisJob?.message || "Запускаем анализ"}</h3>
            <p className="mt-2 leading-relaxed text-[#5f6072]">Сначала система проверит выбранные классы, затем само обозначение и похожие товарные знаки. В конце появится вывод простыми словами.</p>
            <div className="mt-5 h-2.5 w-full max-w-xl overflow-hidden rounded-full bg-white" aria-label={`Анализ выполнен на ${analysisJob?.progress || 5}%`}>
              <div className="h-full rounded-full bg-[#0d9f9b] transition-[width] duration-700 ease-out" style={{ width: `${Math.max(5, analysisJob?.progress || 0)}%` }} />
            </div>
            <p className="mt-2 text-sm font-semibold text-[#087c78]">{Math.max(5, analysisJob?.progress || 0)}%</p>
          </div>
        </div>
      </div>
    </ClientPanel>
  );

  if (loading) return <div className="flex min-h-48 items-center justify-center text-[#6d6d7d]"><Loader2 className="mr-2 h-5 w-5 animate-spin" /> Загружаем результат…</div>;

  if (!presentation) return <ClientPanel title="Результата пока нет" description="Запустите проверку на предыдущем шаге. Система подберёт классы, найдёт сходные товарные знаки и подготовит понятную рекомендацию."><Button onClick={rerun} disabled={running} className="rounded-full bg-[#0d9f9b] px-6 hover:bg-[#078984]">{running ? <Loader2 className="h-4 w-4 animate-spin" /> : <Play className="h-4 w-4" />} Запустить проверку</Button></ClientPanel>;

  const ResultIcon = presentation.icon;
  const visibleRiskFindings = adverseFindings.slice(0, 3);
  const fallbackRisks = adverseFindings.length === 0 && !onlyRoughImageRisks && !incomplete && displayedRisk && displayedRisk !== "low"
    ? (memo?.key_risks_json || []).slice(0, 3)
    : [];
  const hasVisibleRisks = visibleRiskFindings.length > 0 || fallbackRisks.length > 0;
  const approvedClasses = classes.filter((item) => item.approved === true);
  const selectedClassNumbers = new Set(approvedClasses.map((item) => item.class_number));
  const rankedRegistryFindings = [...registryFindings].sort((left, right) => {
    const leftInClasses = left.verification?.search_scope === "selected_classes" ? 1 : 0;
    const rightInClasses = right.verification?.search_scope === "selected_classes" ? 1 : 0;
    if (leftInClasses !== rightInClasses) return rightInClasses - leftInClasses;
    const leftActive = ["registered", "pending"].includes(left.verification?.registry_record?.status || "") ? 1 : 0;
    const rightActive = ["registered", "pending"].includes(right.verification?.registry_record?.status || "") ? 1 : 0;
    return rightActive - leftActive;
  });
  const classLabel = approvedClasses.length === 1
    ? `классе ${approvedClasses[0].class_number}`
    : approvedClasses.length > 1
      ? `классах ${approvedClasses.map((item) => item.class_number).join(", ")}`
    : "выбранных классах";
  const registryAdvice = registrySearchSkipped
    ? (relativeSection?.summary
      || "Поиск похожих знаков не запускался. Сначала нужно устранить препятствие, найденное при проверке самого обозначения, а затем повторить анализ изменённого варианта.")
    : registrySearchComplete
    ? registryFindings.length > 0
      ? `Поиск в ${classLabel} завершён. Среди найденных знаков нет обозначений, которые по предварительной оценке создают высокий риск отказа. Сейчас менять ваше обозначение не требуется.`
      : `Поиск в ${classLabel} завершён. Похожих товарных знаков не найдено. Сейчас менять ваше обозначение не требуется.`
    : "Поиск похожих товарных знаков пока не завершён.";
  const unfinishedLegalCheck = absoluteCheckIncomplete
    ? "Не завершена проверка самостоятельных оснований для отказа по статье 1483 ГК РФ: нужно ещё оценить, не является ли обозначение описательным, общеупотребительным или вводящим в заблуждение. Это не обнаруженный недостаток знака — по этой части пока нет надёжного вывода."
    : externalServicesUnavailable
    ? "Поиск похожих знаков временно не удалось обновить. Это не найденный риск и не недостаток вашего знака. Повторите только этот этап позже."
    : "Одна из предусмотренных проверок пока не завершена. Это не означает, что найдено основание для отказа.";
  const firstSentences = (text: string | null | undefined, count = 1) => {
    if (!text) return "";
    return text.trim().split(/(?<=[.!?])\s+/).slice(0, count).join(" ");
  };
  const clientFinding = (item: RiskFindingSummary) => {
    const record = item.verification?.registry_record;
    if (record?.mark_text) {
      const selected = new Set(classes.filter((entry) => entry.approved === true).map((entry) => entry.class_number));
      const overlap = (record.classes || []).filter((value) => selected.has(Number(value)));
      return `Похожий знак «${record.mark_text}»${overlap.length ? ` найден в ваших классах: ${overlap.join(", ")}` : " требует дополнительной проверки"}.`;
    }
    // Не заменяем конкретный вывод общей заготовкой. Прямое название
    // товара и лишь ассоциативная связь с товаром имеют разные последствия.
    return firstSentences(item.explanation, 1) || "Найдено обстоятельство, которое нужно оценить до подачи заявки.";
  };
  const primaryAdverseFinding = adverseFindings[0];
  const primaryFindingIsAbsolute = Boolean(
    primaryAdverseFinding
    && absoluteSection?.findings?.some((finding) => finding.id === primaryAdverseFinding.id)
  );
  const primarySectionSummary = primaryAdverseFinding
    ? [absoluteSection, effectiveRelativeSection].find((section) =>
        section?.findings?.some((finding) => finding.id === primaryAdverseFinding.id)
      )?.summary
    : null;
  const clientSummary = primarySectionSummary && displayedRisk && ["medium", "high", "critical"].includes(displayedRisk)
    ? (primaryFindingIsAbsolute
      ? `${displayedRisk === "medium" ? "Выявлен риск по абсолютному основанию для отказа." : "Выявлено абсолютное основание для отказа."} ${primarySectionSummary}`
      : primarySectionSummary)
    : displayedRisk ? {
    low: "Серьёзных препятствий не найдено. Можно готовить заявку.",
    medium: "Есть моменты, которые лучше проверить перед подачей.",
    high: "Найдены существенные препятствия. Сначала лучше доработать знак.",
    critical: "В выбранных классах найдены опасные совпадения. Без изменений подавать заявку рискованно.",
  }[displayedRisk] : externalServicesUnavailable && absoluteCheckIncomplete && registrySearchComplete
    ? "Поиск похожих знаков завершён. Проверку самого обозначения пока не удалось закончить; это не означает, что найден риск."
    : externalServicesUnavailable
    ? "Проверка выполнена частично. Готовые результаты сохранены, а незавершённый этап можно повторить."
    : registrySearchComplete
    ? "Поиск сходных знаков завершён. До окончательной рекомендации нужно закончить отдельную правовую проверку самого обозначения."
    : "Проверка выполнена не полностью. Завершите оставшийся шаг.";
  const findingActions = Array.from(new Set(
    adverseFindings
      .map((item) => {
        if (item.category === "descriptive") {
          return "Выбрать фантазийное название, которое не называет товар или услугу напрямую.";
        }
        if (item.category === "against_public_interest") {
          return "Убрать или заменить элемент, который может восприниматься как непристойный или оскорбительный.";
        }
        if (["misleading", "deceptive"].includes(item.category || "")) {
          return "Изменить элемент, который может создать у покупателя неверное представление о товаре или его происхождении.";
        }
        return firstSentences(item.recommended_action || item.recommendation, 1);
      })
      .filter((item): item is string => Boolean(item))
  ));
  const nextSteps = displayedRisk === "critical" || displayedRisk === "high"
    ? (findingActions.length
        ? [...findingActions.slice(0, 2), "Перед подачей повторно проверить изменённый вариант знака."]
        : ["Изменить название или заметные элементы знака.", "Уточнить перечень товаров и услуг — иногда риск можно снизить, сузив его.", "Перед подачей показать новый вариант специалисту."])
    : displayedRisk === "medium"
      ? ["Посмотреть самые важные совпадения ниже.", "При необходимости уточнить товары и услуги.", "После проверки перейти к подготовке заявления."]
      : incomplete
        ? externalServicesUnavailable && absoluteCheckIncomplete
          ? ["Повторить проверку самого обозначения.", "Если она снова не завершится, попросить специалиста оценить обозначение по статье 1483 ГК РФ."]
          : externalServicesUnavailable
          ? ["Повторить поиск похожих товарных знаков.", "Если поиск снова не завершится, попросить специалиста проверить реестр вручную."]
          : ["Повторить только незавершённую проверку — готовый поиск по реестру сохранится.", "Если результат снова не появится, передать обозначение юристу для ручной оценки по статье 1483 ГК РФ."]
        : ["Перейти к расчёту пошлин и проверить доступные льготы.", "После этого скачать комплект документов для подачи."];
  return (
    <ClientPanel title="Результат проверки" description="Коротко: что получилось хорошо, что может помешать регистрации и что делать дальше.">
      <section className={cn("min-w-0 overflow-hidden rounded-[1.5rem] border p-6 sm:p-8", presentation.tone)}>
        <div className="flex min-w-0 items-start gap-4"><span className="flex h-12 w-12 shrink-0 items-center justify-center rounded-full bg-white"><ResultIcon className={cn("h-6 w-6", presentation.color)} /></span><div className="min-w-0"><p className="inline-flex items-center gap-1 text-xs font-bold uppercase tracking-[0.15em] text-[#6d6d7d]">Предварительный вывод <HelpTip text="Это автоматическая предварительная оценка. Окончательное решение принимает Роспатент." /></p><h3 className={cn("mt-1 break-words text-3xl font-semibold", presentation.color)}>{presentation.title}</h3><p className="mt-3 max-w-3xl break-words text-lg leading-relaxed text-[#11113f]">{running ? "Обновляем проверку по подтверждённым данным…" : clientSummary}</p></div></div>
      </section>
      <div className="mt-6 grid min-w-0 grid-cols-1 gap-5 lg:grid-cols-2 min-[1700px]:grid-cols-3">
        <section className={cn("min-w-0 overflow-hidden rounded-[1.3rem] border p-5 [overflow-wrap:anywhere] sm:p-6", registrySearchSkipped || !registrySearchComplete ? "border-amber-200 bg-amber-50/60" : registryResultIsPrevious ? "border-[#0d9f9b]/25 bg-[#eef9f8]" : "border-emerald-200 bg-emerald-50/60")}>
          <h3 className={cn("flex min-w-0 items-start gap-2 text-xl font-semibold", registrySearchSkipped || !registrySearchComplete ? "text-amber-900" : registryResultIsPrevious ? "text-[#087c78]" : "text-emerald-900")}>
            {registrySearchSkipped ? <ShieldAlert className="mt-0.5 h-5 w-5 shrink-0" /> : registrySearchComplete ? <CheckCircle2 className="mt-0.5 h-5 w-5 shrink-0" /> : <AlertCircle className="mt-0.5 h-5 w-5 shrink-0" />}
            {registrySearchSkipped ? "Поиск похожих знаков пока не нужен" : registrySearchComplete ? "Похожие знаки проверены" : "Поиск похожих знаков не завершён"}
          </h3>
          <div className={cn("mt-4 space-y-3 text-sm leading-relaxed", registrySearchSkipped || !registrySearchComplete ? "text-amber-950/80" : "text-emerald-950/80")}>
            <p>{registryAdvice}</p>
            {registryResultIsPrevious && <p className="rounded-lg bg-white/70 px-3 py-2 text-xs font-normal text-[#5f6072]">Не удалось обновить поиск по реестру. Сейчас показан последний успешно полученный результат; его можно обновить ещё раз.</p>}
          </div>
        </section>

        <section className={cn("min-w-0 overflow-hidden rounded-[1.3rem] border p-5 [overflow-wrap:anywhere] sm:p-6", hasVisibleRisks ? "border-red-200 bg-red-50/60" : incomplete ? "border-amber-200 bg-amber-50/60" : "border-emerald-200 bg-emerald-50/60")}>
          <h3 className="flex min-w-0 items-start gap-2 text-xl font-semibold"><AlertCircle className={cn("mt-0.5 h-5 w-5 shrink-0", hasVisibleRisks ? "text-red-600" : incomplete ? "text-amber-600" : "text-emerald-600")} /> {hasVisibleRisks ? "Что может помешать регистрации" : incomplete ? unfinishedCheckTitle : "Юридически значимых рисков не найдено"}</h3>
          <div className="mt-4 space-y-3">
            {visibleRiskFindings.map((item) => (
              <div key={item.id} className="rounded-xl bg-white/75 p-4">
                <p className="mb-2 text-[11px] font-bold uppercase tracking-[0.08em] text-red-700">
                  {absoluteSection?.findings?.some((finding) => finding.id === item.id)
                    ? item.level === "medium"
                      ? "Риск по абсолютному основанию для отказа"
                      : "Абсолютное основание для отказа"
                    : "Риск из-за более раннего товарного знака"}
                </p>
                <p className="text-sm font-medium leading-relaxed text-[#33334f]">{clientFinding(item)}</p>
                {item.legal_basis && <p className="mt-2 text-xs leading-relaxed text-[#6d6d7d]">Норма закона: {item.legal_basis}</p>}
              </div>
            ))}
            {fallbackRisks.map((item, index) => <p key={index} className="text-sm leading-relaxed text-[#55556f]">{item.split(/(?<=[.!?])\s/)[0]}</p>)}
            {!hasVisibleRisks && incomplete && <p className="text-sm leading-relaxed text-amber-900">{unfinishedLegalCheck}</p>}
            {!incomplete && !hasVisibleRisks && <p className="text-sm font-semibold text-emerald-900">Серьёзных препятствий не найдено.</p>}
          </div>
        </section>

        <section className="min-w-0 overflow-hidden rounded-[1.3rem] border border-[#11113f]/10 bg-white p-5 [overflow-wrap:anywhere] sm:p-6 lg:col-span-2 min-[1700px]:col-span-1">
          <h3 className="text-xl font-semibold">Рекомендация</h3>
          <ol className="mt-4 space-y-3">
            {nextSteps.map((step, index) => <li key={step} className="flex gap-3 text-sm leading-relaxed text-[#55556f]"><span className="flex h-6 w-6 shrink-0 items-center justify-center rounded-full bg-[#e8f7f6] text-xs font-bold text-[#087c78]">{index + 1}</span>{step}</li>)}
          </ol>
        </section>
      </div>

      {rankedRegistryFindings.length > 0 && (
        <details className="mt-6 rounded-[1.3rem] border border-[#11113f]/10 bg-white p-5 sm:p-6">
          <summary className="cursor-pointer list-none font-semibold text-[#11113f]">Какие совпадения проверены <span className="ml-2 text-sm font-normal text-[#6d6d7d]">Показать наиболее близкие</span></summary>
          <div className="mt-4 grid gap-3 lg:grid-cols-3">
            {rankedRegistryFindings.slice(0, 3).map((item) => {
              const record = item.verification?.registry_record;
              const overlap = (record?.classes || []).filter((value) => selectedClassNumbers.has(Number(value)));
              const status = record?.status === "pending" ? "заявка рассматривается" : record?.status === "expired" ? "регистрация прекращена" : "зарегистрирован";
              return (
                <article key={item.id} className="rounded-xl bg-[#f8f7f4] p-4">
                  <p className="font-semibold text-[#11113f]">«{record?.mark_text || "Обозначение без названия"}»</p>
                  <p className="mt-1 text-xs text-[#6d6d7d]">{status}{overlap.length ? ` · пересекается класс ${overlap.join(", ")}` : " · вне выбранного класса"}</p>
                  <p className="mt-3 text-sm leading-relaxed text-[#55556f]">Словесная часть и общий смысл отличаются. По предварительной оценке знак не создаёт очевидной вероятности смешения, но учтён в итоговом выводе.</p>
                </article>
              );
            })}
          </div>
        </details>
      )}

      <div className="mt-7 flex flex-col gap-3 rounded-[1.2rem] bg-[#f8f7f4] p-5 sm:flex-row sm:items-center sm:justify-between">
        <p className="max-w-2xl text-sm leading-relaxed text-[#6d6d7d]">Это предварительная проверка по доступным данным. Окончательное решение о регистрации принимает Роспатент.</p>
        <div className="flex shrink-0 flex-wrap gap-2">
          <Button variant="outline" className="rounded-full bg-white" onClick={onReview}>Изменить классы</Button>
          <Button variant="outline" className="rounded-full bg-white" onClick={onEditData}>Изменить данные</Button>
          {retryAvailable && (
            <Button className="rounded-full bg-[#0d9f9b] px-6 hover:bg-[#078984]" onClick={rerun} disabled={running}>{running ? <Loader2 className="h-4 w-4 animate-spin" /> : <RefreshCw className="h-4 w-4" />} {running ? "Обновляем проверку…" : absoluteCheckIncomplete ? "Проверить само обозначение" : registryResultIsPrevious ? "Обновить поиск знаков" : !registrySearchComplete ? "Повторить поиск знаков" : "Повторить проверку"}</Button>
          )}
          {!incomplete && (
            <Button className={cn("rounded-full px-6", retryAvailable ? "border border-[#0d9f9b] bg-white text-[#087c78] hover:bg-[#eaf8f7]" : "bg-[#0d9f9b] text-white hover:bg-[#078984]")} onClick={onApplication}>Перейти к пошлинам <ChevronRight className="h-4 w-4" /></Button>
          )}
        </div>
      </div>
    </ClientPanel>
  );
}

function ClientApplicationStep({ appId, draftRequest, onEditData }: { appId: number; draftRequest: number; onEditData: () => void }) {
  const report = useApi<RiskReport>(`/applications/${appId}/risk-report`);
  return (
    <ClientPanel title="Заявление в Роспатент" description="Проверьте сведения, дополните недостающие поля и скачайте рабочий файл заявления.">
      <ClientDraftPreview
        appId={appId}
        analysisComplete={report.data?.is_complete === true}
        openRequest={Math.max(1, draftRequest)}
        onEditData={onEditData}
      />
    </ClientPanel>
  );
}

interface DraftField {
  inid?: string | null;
  label: string;
  value: string | null;
  fill: string;
  source?: string | null;
  field_path?: string | null;
  extracted_field_id?: number | null;
  editable?: boolean;
  multiline?: boolean;
  hint?: string | null;
  is_sensitive?: boolean;
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

function ClientDraftPreview({
  appId,
  analysisComplete,
  openRequest,
  onEditData,
  onEditClasses,
  application,
  onSaved,
}: {
  appId: number;
  analysisComplete: boolean;
  openRequest: number;
  onEditData: () => void;
  onEditClasses?: () => void;
  application?: Application;
  onSaved?: () => void | Promise<void>;
}) {
  const draft = useApi<DraftForm>(`/applications/${appId}/draft-form`);
  const [open, setOpen] = useState(openRequest > 0);
  const [downloading, setDownloading] = useState(false);
  const [markImageUrl, setMarkImageUrl] = useState<string | null>(null);
  const [editingField, setEditingField] = useState<string | null>(null);
  const [editingValue, setEditingValue] = useState("");
  const [savingField, setSavingField] = useState<string | null>(null);
  const { toast } = useToast();

  const editableSources = new Set([
    "application.applicant.name",
    "application.applicant.inn",
    "application.applicant.ogrn",
    "application.applicant.kpp",
    "application.applicant.address",
    "application.applicant.country_code",
    "application.correspondence_address",
    "application.contact.phone",
    "application.contact.email",
    "application.mark.text",
    "application.mark.description",
    "application.mark.colors",
    "application.mark.transliteration",
    "application.mark.translation",
    "application.mark.kind",
    "application.signatory.name",
    "application.signatory.position",
    "application.signatory.date",
    "application.certificate.paper",
    "application.territory",
  ]);

  const canEditInline = (field: DraftField) => (
    field.fill !== "office"
    && field.fill !== "classes"
    && field.editable !== false
    && (Boolean(field.extracted_field_id) || Boolean(field.source && editableSources.has(field.source)))
  );

  const startFieldEdit = (key: string, field: DraftField) => {
    let value = field.value || "";
    if (field.source === "application.mark.kind" && application?.markType) value = application.markType;
    if (field.source === "application.signatory.date" && application?.signatureDate) value = application.signatureDate;
    if (field.source === "application.certificate.paper") value = application?.requestPaperCertificate ? "true" : "false";
    setEditingValue(value);
    setEditingField(key);
  };

  const saveField = async (key: string, field: DraftField) => {
    const value = editingValue.trim();
    const fieldPath = field.source || field.field_path;
    if (!fieldPath || !value) return;
    setSavingField(key);
    try {
      const requests: Array<Promise<unknown>> = [
        api.post(`/applications/${appId}/fields`, {
          field_path: fieldPath,
          label: field.label,
          value,
          is_sensitive: field.is_sensitive === true,
        }),
      ];
      if (field.extracted_field_id && field.field_path && field.field_path !== fieldPath) {
        requests.push(api.post(`/extracted-fields/${field.extracted_field_id}/confirm`, { action: "edit", value }));
      }
      await Promise.all(requests);
      await onSaved?.();
      await draft.reload();
      setEditingField(null);
      toast({ title: "Поле сохранено", description: "Предпросмотр и готовность документов обновлены." });
    } catch (error) {
      toast({ title: "Не удалось сохранить поле", description: messageOf(error, "Проверьте значение и попробуйте ещё раз"), variant: "destructive" });
    } finally {
      setSavingField(null);
    }
  };

  useEffect(() => {
    let active = true;
    let objectUrl: string | null = null;
    api.blob(`/applications/${appId}/mark-image/content`).then((blob) => {
      if (!active) return;
      objectUrl = URL.createObjectURL(blob);
      setMarkImageUrl(objectUrl);
    }).catch(() => { if (active) setMarkImageUrl(null); });
    return () => {
      active = false;
      if (objectUrl) URL.revokeObjectURL(objectUrl);
    };
  }, [appId]);

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
            <p className="text-xs font-bold uppercase tracking-[0.14em] text-[#087c78]">Перед скачиванием ZIP</p>
            <h3 className="mt-1 text-2xl font-semibold text-[#11113f]">Предпросмотр заявления в Роспатент</h3>
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
          {markImageUrl && (
            <div className="mb-5 rounded-xl border border-[#11113f]/10 bg-[#f8f7f4] p-4">
              <p className="text-sm font-semibold text-[#11113f]">Изображение, которое попадёт в заявление</p>
              <div className="mt-3 flex min-h-44 items-center justify-center rounded-lg border border-[#11113f]/10 bg-white p-4">
                <img src={markImageUrl} alt="Заявляемое обозначение" className="max-h-72 max-w-full object-contain" />
              </div>
              <p className="mt-2 text-xs text-[#6d6d7d]">Показывается только само изображение обозначения — без повторного текстового дубля.</p>
            </div>
          )}
          <div className="mb-5 flex flex-col gap-3 rounded-xl bg-[#f8f7f4] p-4 sm:flex-row sm:items-center sm:justify-between">
            <div>
              <p className="font-semibold text-[#11113f]">Обязательных полей заполнено: {draft.data.required_done} из {draft.data.required_count}</p>
              <p className="mt-1 text-sm text-[#6d6d7d]">{draft.data.can_generate ? "Данных достаточно для формирования чернового файла." : `Нужно дополнить: ${draft.data.blocking.join(", ") || "обязательные сведения"}.`}</p>
            </div>
            {!draft.data.can_generate && <Button variant="outline" className="rounded-full bg-white" onClick={onEditData}><PencilLine className="h-4 w-4" /> Дополнить данные</Button>}
          </div>

          <div className="space-y-5">
            {draft.data.sections.map((section) => {
              const fields = section.fields.filter((field) => field.value || field.required || canEditInline(field) || field.fill === "classes");
              if (!fields.length) return null;
              return <div key={section.id}><h4 className="mb-3 font-semibold text-[#11113f]">{section.title}</h4><div className="grid gap-3 sm:grid-cols-2">{fields.map((field, index) => {
                const key = `${section.id}-${field.source || field.field_path || index}`;
                const isEditing = editingField === key;
                const isSaving = savingField === key;
                const isClasses = field.fill === "classes";
                return <div key={key} className={cn("rounded-xl border p-4 transition-colors", field.needs_attention ? "border-amber-300 bg-amber-50" : isEditing ? "border-[#0d9f9b]/45 bg-[#f4fbfa]" : "border-[#11113f]/10 bg-white")}>
                  <div className="flex items-start justify-between gap-2"><div className="flex min-w-0 items-center gap-2"><p className="text-sm font-semibold text-[#11113f]">{field.label}</p>{field.inid && <span className="rounded border border-[#11113f]/15 px-1.5 py-0.5 text-[9px] font-bold text-[#77778a]">{field.inid}</span>}</div>{field.needs_attention ? <span className="shrink-0 rounded-full bg-amber-100 px-2 py-1 text-[10px] font-bold text-amber-800">Нужно заполнить</span> : <CheckCircle2 className="h-4 w-4 shrink-0 text-emerald-600" />}</div>
                  {isEditing ? <div className="mt-3">
                    {field.source === "application.mark.kind" ? <Select value={editingValue} onValueChange={setEditingValue}><SelectTrigger className="bg-white"><SelectValue /></SelectTrigger><SelectContent>{Object.entries(MARK_TYPE_LABELS).map(([value, label]) => <SelectItem key={value} value={value}>{label}</SelectItem>)}</SelectContent></Select> : field.source === "application.certificate.paper" ? <Select value={editingValue} onValueChange={setEditingValue}><SelectTrigger className="bg-white"><SelectValue /></SelectTrigger><SelectContent><SelectItem value="false">Только электронное свидетельство</SelectItem><SelectItem value="true">Нужно бумажное свидетельство</SelectItem></SelectContent></Select> : field.source === "application.signatory.date" ? <Input type="date" className="bg-white" value={editingValue} onChange={(event) => setEditingValue(event.target.value)} /> : field.multiline || (field.value?.length || 0) > 120 ? <Textarea autoFocus rows={4} className="bg-white" value={editingValue} onChange={(event) => setEditingValue(event.target.value)} /> : <Input autoFocus className="bg-white" value={editingValue} onChange={(event) => setEditingValue(event.target.value)} />}
                    {field.hint && <p className="mt-2 text-xs leading-relaxed text-[#6d6d7d]">{field.hint}</p>}
                    <div className="mt-3 flex flex-wrap gap-2"><Button size="sm" className="rounded-full" disabled={isSaving || !editingValue.trim()} onClick={() => void saveField(key, field)}>{isSaving ? <Loader2 className="h-4 w-4 animate-spin" /> : <Check className="h-4 w-4" />} {isSaving ? "Сохраняем…" : "Сохранить"}</Button><Button size="sm" variant="ghost" className="rounded-full" disabled={isSaving} onClick={() => setEditingField(null)}>Отмена</Button></div>
                  </div> : <>
                    <p className="mt-2 whitespace-pre-wrap text-sm leading-relaxed text-[#55556f]">{field.value || "Пока не заполнено"}</p>
                    <div className="mt-3 flex flex-wrap items-center justify-between gap-2">{field.value ? <p className="text-[11px] text-[#77778a]">{field.origin ? `Источник: ${field.origin}` : "Взято из данных заявки"}</p> : <span />}
                      {canEditInline(field) ? <Button size="sm" variant="ghost" className="h-8 rounded-full px-3 text-xs text-[#087c78]" onClick={() => startFieldEdit(key, field)}><PencilLine className="h-3.5 w-3.5" /> {field.value ? "Изменить" : "Заполнить"}</Button> : isClasses && onEditClasses ? <Button size="sm" variant="ghost" className="h-8 rounded-full px-3 text-xs text-[#087c78]" onClick={onEditClasses}><PencilLine className="h-3.5 w-3.5" /> Изменить перечень</Button> : null}
                    </div>
                  </>}
                </div>;
              })}</div></div>;
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
  paper_certificate_requested: boolean;
  total_selected: number | null;
  calculated_at: string;
  source_url: string;
  warnings: string[];
  term_surcharge?: number;
  classes?: Array<{ class_number: number; term_count: number; extra_terms_over_10: number }>;
}

const rubles = (value: number | null) => value == null ? "—" : `${new Intl.NumberFormat("ru-RU").format(value)} ₽`;

function ClientFeeEstimate({ appId, onDocuments, onReview }: { appId: number; onDocuments: () => void; onReview: () => void }) {
  const fees = useApi<FeeEstimate>(`/applications/${appId}/fees`);
  const savedBenefit = useMemo(() => {
    try {
      return JSON.parse(localStorage.getItem(`registr:fee-benefit:${appId}`) || "null") as { open?: boolean; value?: string } | null;
    } catch { return null; }
  }, [appId]);
  const [benefitOpen, setBenefitOpen] = useState(savedBenefit?.open === true);
  const [benefit, setBenefit] = useState(savedBenefit?.value || "regular");

  useEffect(() => {
    try {
      localStorage.setItem(`registr:fee-benefit:${appId}`, JSON.stringify({ open: benefitOpen, value: benefit }));
    } catch { /* Приватный режим может запрещать локальное хранилище. */ }
  }, [appId, benefitOpen, benefit]);
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
          <div className="rounded-xl bg-[#11113f] p-4 text-white"><p className="text-xs text-white/65">{fees.data.paper_certificate_requested ? "Всего с бумажным свидетельством" : "Всего, электронное свидетельство"}</p><p className="mt-1 text-2xl font-semibold">{rubles(fees.data.total_selected ?? fees.data.total_electronic)}</p></div>
        </div>
          <div className="mt-5 space-y-2">{fees.data.payments.map((payment) => <div key={payment.code} className="flex flex-col justify-between gap-1 border-b border-[#11113f]/8 py-3 text-sm sm:flex-row sm:items-center"><div><span className="font-semibold">{payment.title}</span><span className="ml-2 text-xs text-[#77778a]">подп. {payment.code} приложения № 1 к Положению о пошлинах</span><p className="mt-1 text-xs text-[#77778a]">{payment.when}</p></div><span className="font-semibold text-[#11113f]">{rubles(payment.amount)}</span></div>)}</div>
        {(fees.data.term_surcharge || 0) > 0 && (
          <div className="mt-5 rounded-xl border-2 border-amber-300 bg-amber-50 p-4 sm:p-5">
            <div className="flex flex-col gap-4 sm:flex-row sm:items-start sm:justify-between">
              <div>
                <p className="flex items-center gap-2 font-semibold text-amber-950"><AlertCircle className="h-5 w-5" /> Почему экспертиза получилась такой дорогой</p>
                <p className="mt-2 text-sm leading-relaxed text-amber-950/85">Базовая экспертиза одного класса стоит 13 000 ₽. В выбранный перечень включено больше десяти наименований, поэтому Роспатент добавляет 500 ₽ за каждое следующее.</p>
              </div>
              <Button type="button" variant="outline" className="shrink-0 rounded-full border-amber-400 bg-white" onClick={onReview}>Проверить перечень</Button>
            </div>
            <div className="mt-4 grid gap-2 sm:grid-cols-2">
              {(fees.data.classes || []).filter((item) => item.extra_terms_over_10 > 0).map((item) => (
                <div key={item.class_number} className="rounded-lg bg-white p-3 text-sm text-[#44445d]">
                  <p className="font-semibold text-[#11113f]">Класс {item.class_number}: {item.term_count} наименований</p>
                  <p className="mt-1 text-xs leading-relaxed">Доплата: {item.extra_terms_over_10} × 500 ₽ = {rubles(item.extra_terms_over_10 * 500)}</p>
                </div>
              ))}
              <div className="rounded-lg bg-[#11113f] p-3 text-white">
                <p className="text-xs text-white/65">Доплата за расширенный перечень</p>
                <p className="mt-1 text-xl font-semibold">{rubles(fees.data.term_surcharge || 0)}</p>
              </div>
            </div>
            <p className="mt-3 text-xs leading-relaxed text-amber-950/80"><strong>Важно:</strong> удаляйте только товары и услуги, которыми вы действительно не занимаетесь и не планируете заниматься. Меньший перечень снижает пошлину, но знак не будет защищён для исключённых позиций.</p>
          </div>
        )}
        <p className="mt-4 text-sm text-[#55556f]">Расчёт для {fees.data.class_count} кл. МКТУ. {fees.data.paper_certificate_requested ? `Вы выбрали бумажное свидетельство: в итог включено ${rubles(fees.data.paper_certificate_extra)}.` : `Бумажное свидетельство не выбрано; при необходимости его можно заказать за ${rubles(fees.data.paper_certificate_extra)}.`}</p>
        <div className="mt-5 rounded-xl border border-[#11113f]/10 p-4">
          <div className="flex flex-wrap items-center justify-between gap-3"><div><p className="font-semibold text-[#11113f]">Какие льготы возможны?</p><p className="mt-1 text-xs text-[#6d6d7d]">Для обычной заявки на товарный знак льгот немного. Проверьте, относится ли заявитель к одной из специальных категорий.</p></div><Button type="button" variant="outline" onClick={() => setBenefitOpen((value) => !value)}>{benefitOpen ? "Скрыть" : "Проверить моё основание"}</Button></div>
          <div className="mt-4 grid gap-3 sm:grid-cols-2">
            <div className="rounded-lg bg-[#f8f7f4] p-3 text-xs leading-relaxed text-[#44445d]"><p className="font-semibold text-[#11113f]">Освобождение от части пошлин</p><p className="mt-1">Может применяться к федеральным и региональным органам власти, а также к «Росатому» и «Роскосмосу» при управлении правами Российской Федерации.</p></div>
            <div className="rounded-lg bg-[#f8f7f4] p-3 text-xs leading-relaxed text-[#44445d]"><p className="font-semibold text-[#11113f]">Кому общая льгота не предоставляется</p><p className="mt-1">Статус физлица, самозанятого, ИП, субъекта МСП, пенсионера, студента, инвалида или ветерана сам по себе не уменьшает пошлины за регистрацию товарного знака.</p></div>
          </div>
          {benefitOpen && <div className="mt-4 space-y-3"><Select value={benefit} onValueChange={setBenefit}><SelectTrigger><SelectValue /></SelectTrigger><SelectContent><SelectItem value="regular">Обычный заявитель: физлицо, самозанятый, ИП или организация</SelectItem><SelectItem value="authority">Федеральный или региональный орган власти</SelectItem><SelectItem value="corporation">«Росатом» или «Роскосмос» при управлении правами РФ</SelectItem><SelectItem value="unsure">Не уверен — нужна проверка</SelectItem></SelectContent></Select><div className="rounded-lg bg-amber-50 p-3 text-xs leading-relaxed text-amber-900">{benefit === "authority" || benefit === "corporation" ? "Возможно освобождение от пошлины за экспертизу обозначения. Потребуется ходатайство и подтверждение статуса или полномочий заявителя. Расчёт не будет уменьшен, пока основание не подтверждено." : benefit === "unsure" ? "Не оплачивайте меньшую сумму самостоятельно. Передайте специалисту сведения о заявителе и документ, на котором, по вашему мнению, основана льгота." : "Для этой категории общей льготы на регистрацию товарного знака нет. Рассчитывайте полную сумму, указанную выше."}</div><p className="flex items-center gap-2 text-xs font-medium text-[#087c78]"><CheckCircle2 className="h-4 w-4" /> Выбор сохранён в черновике на этом устройстве.</p></div>}
        </div>
        <div className="mt-4 rounded-xl bg-amber-50 p-4 text-xs leading-relaxed text-amber-900">{fees.data.warnings.map((warning) => <p key={warning}>• {warning}</p>)}</div>
        <div className="mt-5 flex flex-wrap items-center justify-between gap-3">
          <a href={fees.data.source_url} target="_blank" rel="noreferrer" className="text-xs font-semibold text-[#087c78] underline underline-offset-4">Официальная таблица пошлин Роспатента ↗</a>
          <Button className="rounded-full bg-[#0d9f9b] px-6 hover:bg-[#078984]" onClick={onDocuments}>Перейти к документам <ChevronRight className="h-4 w-4" /></Button>
        </div>
      </div>}
      {fees.error && <div className="border-t border-red-200 bg-red-50 p-5 text-sm text-red-800">Не удалось рассчитать пошлины: {fees.error}</div>}
    </section>
  );
}

interface FilingPackageStatus {
  ready: boolean;
  blockers: Array<{ code: string; title: string; action: string; section: string }>;
  warnings: string[];
  documents: Array<{ filename: string; title: string; folder: string; purpose: string }>;
  excluded_documents?: Array<{ filename: string; title: string; reason: string }>;
  filing_document_count: number;
  reference_document_count: number;
  class_numbers: number[];
  overall_risk: string | null;
  filing_fee: number | null;
  registration_fee: number | null;
  total_fee: number | null;
  field_sources?: {
    version: string;
    fields: FieldSourceDto[];
  };
  requirements?: {
    version: string;
    applicant_type: string | null;
    mark_type: string | null;
    filing_method: string;
    requirements: Array<{
      code: string;
      title: string;
      action: string;
      section: string;
      kind: string;
      applicable: boolean;
      required: boolean;
      satisfied: boolean;
    }>;
  };
}

function ClientFilingPackage({
  appId,
  application,
  client,
  onSaved,
  onGoToSection,
}: {
  appId: number;
  application: Application;
  client: Client | null;
  onSaved: () => void | Promise<void>;
  onGoToSection: (section: Section) => void;
}) {
  const pack = useApi<FilingPackageStatus>(`/applications/${appId}/filing-package`);
  const [downloading, setDownloading] = useState(false);
  const [savingMissing, setSavingMissing] = useState(false);
  const [uploadingMissing, setUploadingMissing] = useState<string | null>(null);
  const [completion, setCompletion] = useState({
    applicantName: client?.fullNameOrCompanyName || "",
    inn: client?.inn || "",
    ogrn: client?.ogrnOrOgrnip || "",
    kpp: client?.kpp || "",
    address: client?.address || "",
    country: client?.countryCode || "RU",
    email: client?.email || "",
    phone: client?.phone || "",
    territory: application.territory || "Россия",
    markDescription: application.descriptionOfMark || "",
    signatoryName: application.signatoryName || (client?.type === "company" ? "" : client?.fullNameOrCompanyName || ""),
    signatoryPosition: application.signatoryPosition || "",
    signatureDate: application.signatureDate || new Date().toISOString().slice(0, 10),
  });
  const { toast } = useToast();

  useEffect(() => {
    setCompletion({
      applicantName: client?.fullNameOrCompanyName || "",
      inn: client?.inn || "",
      ogrn: client?.ogrnOrOgrnip || "",
      kpp: client?.kpp || "",
      address: client?.address || "",
      country: client?.countryCode || "RU",
      email: client?.email || "",
      phone: client?.phone || "",
      territory: application.territory || "Россия",
      markDescription: application.descriptionOfMark || "",
      signatoryName: application.signatoryName || (client?.type === "company" ? "" : client?.fullNameOrCompanyName || ""),
      signatoryPosition: application.signatoryPosition || "",
      signatureDate: application.signatureDate || new Date().toISOString().slice(0, 10),
    });
  }, [application.updatedAt, client?.id, client?.fullNameOrCompanyName, client?.address]);

  const blockerCodes = new Set(pack.data?.blockers.map((item) => item.code) || []);
  const hasGenericRequiredFields = blockerCodes.has("required_field");
  const hasInlineTextFields = hasGenericRequiredFields || [
    "territory",
    "mark_description",
    "signatory_name",
    "signatory_position",
    "signature_date",
  ].some((code) => blockerCodes.has(code));
  const uploadBlockers = pack.data?.blockers.filter((item) =>
    ["mark_image", "mark_audio", "power_of_attorney", "priority_proof"].includes(item.code),
  ) || [];
  const checkBlockers = pack.data?.blockers.filter((item) => item.section === "check") || [];
  const feeBlockers = pack.data?.blockers.filter((item) => item.section === "fees") || [];

  const saveMissingFields = async () => {
    if (!completion.applicantName.trim()) {
      toast({ title: "Укажите заявителя", description: "Наименование организации или ФИО обязательны для заявления.", variant: "destructive" });
      return;
    }
    setSavingMissing(true);
    try {
      await Promise.all([
        client ? api.put(`/clients/${client.id}`, {
          full_name_or_company_name: completion.applicantName.trim(),
          inn: completion.inn.trim() || null,
          ogrn_or_ogrnip: completion.ogrn.trim() || null,
          kpp: completion.kpp.trim() || null,
          address: completion.address.trim() || null,
          country: completion.country || "RU",
          email: completion.email.trim() || null,
          phone: completion.phone.trim() || null,
        }) : Promise.resolve(),
        api.put(`/applications/${appId}`, {
          territory: completion.territory.trim() || "Россия",
          description_of_mark: completion.markDescription.trim() || null,
          signatory_name: completion.signatoryName.trim() || null,
          signatory_position: completion.signatoryPosition.trim() || null,
          signature_date: completion.signatureDate || null,
        }),
      ]);
      await onSaved();
      await pack.reload();
      toast({ title: "Данные сохранены", description: "Повторно проверяем готовность документов." });
    } catch (error) {
      toast({ title: "Не удалось сохранить", description: messageOf(error, "Проверьте поля и попробуйте ещё раз"), variant: "destructive" });
    } finally {
      setSavingMissing(false);
    }
  };

  const uploadMissingFile = async (code: string, file?: File) => {
    if (!file) return;
    setUploadingMissing(code);
    try {
      if (code === "mark_image") {
        await api.upload(`/applications/${appId}/mark-image`, file);
      } else {
        const document = await api.upload<SourceDocumentDto>(`/applications/${appId}/source-documents`, file);
        const kind = code === "power_of_attorney" ? "power_of_attorney" : code === "priority_proof" ? "other" : null;
        if (kind) await api.put(`/source-documents/${document.id}/kind`, { document_kind: kind });
      }
      pack.reload();
      toast({ title: "Файл добавлен", description: "Повторно проверяем комплект документов." });
    } catch (error) {
      toast({ title: "Не удалось добавить файл", description: messageOf(error, "Проверьте формат файла и попробуйте снова"), variant: "destructive" });
    } finally {
      setUploadingMissing(null);
    }
  };

  const download = async () => {
    setDownloading(true);
    try {
      await api.download(
        `/applications/${appId}/filing-package/download`,
        `paket-dlya-podachi-${appId}.zip`,
      );
      toast({
        title: "Полный пакет скачан",
        description: "Начните с инструкции в папке «02_ДЛЯ_ВАС». В Роспатент направляются только применимые файлы из папки «01_ДЛЯ_ПОДАЧИ».",
      });
    } catch (error) {
      toast({
        title: "Пакет пока не скачан",
        description: messageOf(error, "Проверьте незавершённые пункты и попробуйте снова"),
        variant: "destructive",
      });
      pack.reload();
    } finally {
      setDownloading(false);
    }
  };

  return (
    <>
    <ClientDraftPreview
      appId={appId}
      analysisComplete
      openRequest={1}
      application={application}
      onEditData={() => onGoToSection("review")}
      onEditClasses={() => onGoToSection("review")}
      onSaved={async () => {
        await onSaved();
        await pack.reload();
      }}
    />
    <section className={cn(
      "mt-6 overflow-hidden rounded-[1.5rem] border-2",
      pack.data?.ready ? "border-emerald-300 bg-emerald-50" : "border-amber-200 bg-amber-50",
    )}>
      <div className="flex flex-col gap-5 p-6 sm:p-7 lg:flex-row lg:items-start lg:justify-between">
        <div className="flex items-start gap-4">
          <span className={cn(
            "flex h-12 w-12 shrink-0 items-center justify-center rounded-full bg-white",
            pack.data?.ready ? "text-emerald-700" : "text-amber-700",
          )}>
            {pack.data?.ready ? <BookOpenCheck className="h-6 w-6" /> : <Archive className="h-6 w-6" />}
          </span>
          <div>
            <p className={cn(
              "text-xs font-bold uppercase tracking-[0.14em]",
              pack.data?.ready ? "text-emerald-700" : "text-amber-700",
            )}>Финальный этап</p>
            <h3 className="mt-1 text-2xl font-semibold text-[#11113f]">{pack.data?.ready ? "Можно скачать документы" : "Подготовка документов"}</h3>
            <p className="mt-2 max-w-2xl text-sm text-[#55556f]">В одном ZIP: заявление, нужные приложения и простая инструкция по подаче.</p>
          </div>
        </div>
        <div className="flex shrink-0 flex-wrap gap-2">
          <Button variant="outline" className="rounded-full bg-white" onClick={pack.reload} disabled={pack.isLoading}>
            <RefreshCw className={cn("h-4 w-4", pack.isLoading && "animate-spin")} /> Проверить
          </Button>
          <Button
            className="rounded-full bg-[#0d9f9b] px-6 hover:bg-[#078984]"
            disabled={!pack.data?.ready || downloading}
            onClick={() => void download()}
          >
            {downloading ? <Loader2 className="h-4 w-4 animate-spin" /> : <Download className="h-4 w-4" />}
            Скачать полный ZIP
          </Button>
        </div>
      </div>

      {pack.isLoading && <div className="border-t border-black/10 bg-white/60 p-6 text-sm text-[#6d6d7d]"><Loader2 className="mr-2 inline h-4 w-4 animate-spin" /> Проверяем комплектность документов…</div>}
      {pack.error && <div className="border-t border-red-200 bg-red-50 p-5 text-sm text-red-800">Не удалось проверить пакет: {pack.error}</div>}

      {pack.data && (
        <div className="border-t border-black/10 bg-white p-5 sm:p-6">
          {pack.data.ready ? (
            <div className="mb-6 grid gap-3 sm:grid-cols-3">
              <div className="rounded-xl bg-[#f4f8f7] p-4"><p className="text-xs text-[#6d6d7d]">Для подачи</p><p className="mt-1 text-2xl font-semibold">{pack.data.filing_document_count} файла</p></div>
              <div className="rounded-xl bg-[#f4f8f7] p-4"><p className="text-xs text-[#6d6d7d]">Инструкции и расчёты</p><p className="mt-1 text-2xl font-semibold">{pack.data.reference_document_count} файла</p></div>
              <div className="rounded-xl bg-[#11113f] p-4 text-white"><p className="text-xs text-white/65">К оплате при подаче</p><p className="mt-1 text-2xl font-semibold">{rubles(pack.data.filing_fee)}</p></div>
            </div>
          ) : (
            <div className="mb-6 rounded-xl border border-amber-200 bg-amber-50 p-4">
              <p className="font-semibold text-amber-950">Осталось сделать: {pack.data.blockers.length}</p>
              <div className="mt-3 space-y-2">
                {pack.data.blockers.map((item, index) => (
                  <div key={`${item.code}-${index}`} className="flex items-start gap-3 rounded-lg bg-white px-4 py-3 text-sm">
                    <AlertCircle className="mt-0.5 h-4 w-4 shrink-0 text-amber-700" />
                    <div><p className="font-semibold text-[#11113f]">{item.title}</p><p className="mt-0.5 text-[#6d6d7d]">{item.action}</p></div>
                  </div>
                ))}
              </div>
              {hasInlineTextFields && (
                <div className="mt-5 rounded-xl border border-amber-200 bg-white p-4 sm:p-5">
                  <div>
                    <p className="font-semibold text-[#11113f]">Дополните сведения здесь</p>
                    <p className="mt-1 text-xs leading-relaxed text-[#6d6d7d]">После сохранения экран сам повторно проверит пакет. Возвращаться к началу заявки не нужно.</p>
                  </div>
                  <div className="mt-4 grid gap-4 sm:grid-cols-2">
                    {hasGenericRequiredFields && <MarkedField label="Наименование или ФИО заявителя" mode="manual"><Input value={completion.applicantName} onChange={(event) => setCompletion((old) => ({ ...old, applicantName: event.target.value }))} /></MarkedField>}
                    {hasGenericRequiredFields && <MarkedField label="ИНН" mode="manual"><Input value={completion.inn} onChange={(event) => setCompletion((old) => ({ ...old, inn: event.target.value }))} /></MarkedField>}
                    {hasGenericRequiredFields && <MarkedField label="ОГРН / ОГРНИП" mode="manual"><Input value={completion.ogrn} onChange={(event) => setCompletion((old) => ({ ...old, ogrn: event.target.value }))} /></MarkedField>}
                    {hasGenericRequiredFields && client?.type === "company" && <MarkedField label="КПП" mode="manual"><Input value={completion.kpp} onChange={(event) => setCompletion((old) => ({ ...old, kpp: event.target.value }))} /></MarkedField>}
                    {hasGenericRequiredFields && <div className="sm:col-span-2"><MarkedField label="Адрес заявителя" mode="manual"><Input value={completion.address} onChange={(event) => setCompletion((old) => ({ ...old, address: event.target.value }))} /></MarkedField></div>}
                    {hasGenericRequiredFields && <MarkedField label="Код страны" mode="manual"><select value={completion.country} onChange={(event) => setCompletion((old) => ({ ...old, country: event.target.value }))} className="flex h-10 w-full rounded-md border border-input bg-background px-3 py-2 text-sm">{COUNTRY_OPTIONS.map((country) => <option key={country.code} value={country.code}>{country.name} — {country.code}</option>)}</select></MarkedField>}
                    {hasGenericRequiredFields && <MarkedField label="E-mail" mode="manual"><Input type="email" value={completion.email} onChange={(event) => setCompletion((old) => ({ ...old, email: event.target.value }))} /></MarkedField>}
                    {hasGenericRequiredFields && <MarkedField label="Телефон" mode="manual"><Input value={completion.phone} onChange={(event) => setCompletion((old) => ({ ...old, phone: event.target.value }))} /></MarkedField>}
                    {blockerCodes.has("territory") && <MarkedField label="Территория регистрации" mode="manual"><Input value={completion.territory} onChange={(event) => setCompletion((old) => ({ ...old, territory: event.target.value }))} /></MarkedField>}
                    {blockerCodes.has("mark_description") && <div className="sm:col-span-2"><MarkedField label="Описание обозначения" mode="manual"><Textarea rows={4} value={completion.markDescription} onChange={(event) => setCompletion((old) => ({ ...old, markDescription: event.target.value }))} /></MarkedField></div>}
                    {blockerCodes.has("signatory_name") && <MarkedField label="ФИО подписанта" mode="manual"><Input value={completion.signatoryName} onChange={(event) => setCompletion((old) => ({ ...old, signatoryName: event.target.value }))} /></MarkedField>}
                    {blockerCodes.has("signatory_position") && <MarkedField label="Должность подписанта" mode="manual"><Input value={completion.signatoryPosition} onChange={(event) => setCompletion((old) => ({ ...old, signatoryPosition: event.target.value }))} /></MarkedField>}
                    {blockerCodes.has("signature_date") && <MarkedField label="Дата подписания" mode="manual"><Input type="date" value={completion.signatureDate} onChange={(event) => setCompletion((old) => ({ ...old, signatureDate: event.target.value }))} /></MarkedField>}
                  </div>
                  <Button className="mt-4 rounded-full bg-[#0d9f9b] px-6 hover:bg-[#078984]" disabled={savingMissing} onClick={() => void saveMissingFields()}>{savingMissing ? <Loader2 className="h-4 w-4 animate-spin" /> : <Check className="h-4 w-4" />} {savingMissing ? "Сохраняем…" : "Сохранить и проверить пакет"}</Button>
                </div>
              )}

              {uploadBlockers.length > 0 && (
                <div className="mt-4 space-y-2">
                  {uploadBlockers.map((item) => (
                    <div key={item.code} className="flex flex-col gap-3 rounded-xl border border-amber-200 bg-white p-4 sm:flex-row sm:items-center sm:justify-between">
                      <div><p className="font-semibold text-[#11113f]">{item.title}</p><p className="mt-1 text-xs text-[#6d6d7d]">{item.action}</p></div>
                      <label className="inline-flex cursor-pointer items-center justify-center gap-2 rounded-full border border-[#11113f]/15 bg-white px-4 py-2 text-sm font-semibold hover:bg-[#f8f7f4]">
                        {uploadingMissing === item.code ? <Loader2 className="h-4 w-4 animate-spin" /> : <Upload className="h-4 w-4" />} {uploadingMissing === item.code ? "Загружаем…" : "Добавить файл"}
                        <input type="file" className="sr-only" disabled={uploadingMissing !== null} accept={item.code === "mark_image" ? "image/png,image/jpeg" : item.code === "mark_audio" ? "audio/mpeg,audio/wav" : ".pdf,.docx,.txt,.png,.jpg,.jpeg"} onChange={(event) => void uploadMissingFile(item.code, event.target.files?.[0])} />
                      </label>
                    </div>
                  ))}
                </div>
              )}

              {checkBlockers.length > 0 && (
                <div className="mt-4 flex flex-col gap-3 rounded-xl border border-[#11113f]/10 bg-white p-4 sm:flex-row sm:items-center sm:justify-between">
                  <div><p className="font-semibold text-[#11113f]">Нужно завершить проверку</p><p className="mt-1 text-xs text-[#6d6d7d]">Классы и юридический анализ подтверждаются на предыдущем экране — загружать материалы заново не потребуется.</p></div>
                  <Button variant="outline" className="shrink-0 rounded-full bg-white" onClick={() => onGoToSection("review")}><ChevronRight className="h-4 w-4" /> Перейти к проверке</Button>
                </div>
              )}

              {feeBlockers.length > 0 && (
                <div className="mt-4 flex flex-col gap-3 rounded-xl border border-[#11113f]/10 bg-white p-4 sm:flex-row sm:items-center sm:justify-between">
                  <div><p className="font-semibold text-[#11113f]">Нужно проверить пошлины</p><p className="mt-1 text-xs text-[#6d6d7d]">Откройте расчёт, проверьте выбранные классы и вернитесь к документам.</p></div>
                  <Button variant="outline" className="shrink-0 rounded-full bg-white" onClick={() => onGoToSection("fees")}><ChevronRight className="h-4 w-4" /> Перейти к пошлинам</Button>
                </div>
              )}
            </div>
          )}

          <details className="rounded-xl border border-[#11113f]/10 p-4">
            <summary className="cursor-pointer font-semibold text-[#11113f]">Что войдёт в ZIP</summary>
          <div className="mt-5 grid gap-5 lg:grid-cols-2">
            <div>
              <h4 className="font-semibold text-[#11113f]">01 — Для подачи в Роспатент</h4>
              <p className="mt-1 text-xs leading-relaxed text-[#6d6d7d]">Только эти применимые файлы переносятся в официальный сервис.</p>
              <div className="mt-3 space-y-2">
                {pack.data.documents.filter((item) => item.folder === "01_ДЛЯ_ПОДАЧИ").map((item) => (
                  <div key={`${item.folder}-${item.filename}`} className="rounded-xl border border-[#11113f]/10 p-3">
                    <p className="text-sm font-semibold">{item.title}</p><p className="mt-1 text-xs text-[#6d6d7d]">{item.purpose}</p>
                  </div>
                ))}
              </div>
            </div>
            <div>
              <h4 className="font-semibold text-[#11113f]">02 — Для вас</h4>
              <p className="mt-1 text-xs leading-relaxed text-[#6d6d7d]">Эти материалы объясняют порядок действий и не прикладываются к заявке.</p>
              <div className="mt-3 space-y-2">
                {pack.data.documents.filter((item) => item.folder === "02_ДЛЯ_ВАС").map((item) => (
                  <div key={`${item.folder}-${item.filename}`} className="rounded-xl border border-[#11113f]/10 p-3">
                    <p className="text-sm font-semibold">{item.title}</p><p className="mt-1 text-xs text-[#6d6d7d]">{item.purpose}</p>
                  </div>
                ))}
              </div>
            </div>
          </div>
          </details>

          {(pack.data.excluded_documents || []).length > 0 && (
            <div className="mt-5 rounded-xl border border-sky-200 bg-sky-50 p-4">
              <p className="flex items-center gap-2 font-semibold text-sky-950"><LockKeyhole className="h-4 w-4" /> Чувствительные документы не войдут в ZIP</p>
              <div className="mt-3 space-y-2">
                {(pack.data.excluded_documents || []).map((item) => (
                  <div key={item.filename} className="rounded-lg bg-white px-4 py-3 text-sm">
                    <p className="font-semibold text-[#11113f]">{item.title}: {item.filename}</p>
                    <p className="mt-1 text-xs leading-relaxed text-[#5f6072]">{item.reason}</p>
                  </div>
                ))}
              </div>
            </div>
          )}

          {pack.data.warnings.length > 0 && <details className="mt-5 rounded-xl bg-[#f8f7f4] p-4 text-xs text-[#55556f]"><summary className="cursor-pointer font-semibold text-[#11113f]">Важные примечания ({pack.data.warnings.length})</summary><div className="mt-3 space-y-2 leading-relaxed">{pack.data.warnings.map((warning) => <p key={warning}>• {warning}</p>)}</div></details>}

          <div className="mt-5 flex flex-col gap-3 rounded-xl border border-[#11113f]/10 bg-[#f8f7f4] p-4 sm:flex-row sm:items-center sm:justify-between">
            <div><p className="font-semibold text-[#11113f]">Если после подачи придёт уведомление Роспатента</p><p className="mt-1 text-xs leading-relaxed text-[#6d6d7d]">Загрузите его в отдельном разделе — черновик ответа и приложенные доказательства сохранятся в этой заявке.</p></div>
            <Button variant="outline" className="shrink-0 rounded-full bg-white" onClick={() => onGoToSection("response")}><MessageSquareText className="h-4 w-4" /> Перейти к ответу</Button>
          </div>
        </div>
      )}
    </section>
    </>
  );
}
