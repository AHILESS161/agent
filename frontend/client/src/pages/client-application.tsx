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
import { Badge } from "@/components/ui/badge";
import { useToast } from "@/hooks/use-toast";
import { api, ApiError, DOCUMENT_KIND_LABELS, type ReconciliationDto, type SourceDocumentDto } from "@/lib/api";
import { useCase } from "@/lib/use-cases";
import { cn } from "@/lib/utils";
import { HelpTip } from "@/components/help-tip";
import { useApi } from "@/lib/use-api";
import { COUNTRY_OPTIONS } from "@/lib/country-codes";
import { MARK_TYPE_LABELS, type MarkType } from "@shared/schema";
import { OfficeActionResponse } from "@/components/office-action-response";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";

type Section = "data" | "check" | "application" | "fees" | "documents" | "response";

interface ClassSuggestion {
  id: number;
  class_number: number;
  class_description: string | null;
  rationale: string | null;
  approved: boolean | null;
}

interface RiskFindingSummary {
  id: number;
  explanation: string;
  recommendation?: string;
  level?: string;
  verification?: {
    registry_record?: { mark_text?: string; classes?: Array<number | string>; owner?: string };
    image_comparison?: { score: number } | null;
  };
}

interface RiskReport {
  overall_risk: "low" | "medium" | "high" | "critical" | null;
  is_complete: boolean;
  incomplete_checks?: string[];
  sections: Record<string, {
    findings?: RiskFindingSummary[];
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

interface RegistrantPrefillDto {
  document_kind: string | null;
  prefill: {
    name?: string;
    inn?: string;
    ogrn?: string;
    address?: string;
    business_activity?: string;
  };
  warning: string | null;
}

const SECTION_META: Array<{ id: Section; label: string; icon: typeof Circle }> = [
  { id: "data", label: "Данные", icon: PencilLine },
  { id: "check", label: "Проверка", icon: Sparkles },
  { id: "application", label: "Заявка", icon: FileSignature },
  { id: "fees", label: "Пошлины", icon: ReceiptText },
  { id: "documents", label: "Документы", icon: Archive },
  { id: "response", label: "Ответ Роспатенту", icon: MessageSquareText },
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
            <button type="button" onClick={() => { setDraftRequest((value) => value + 1); setSection("application"); }} className="text-sm font-semibold text-[#43c7c2] underline decoration-[#43c7c2]/40 underline-offset-4 hover:text-white">
              Открыть черновик заявления →
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
        {section === "check" && <ClientCheck appId={appId} onResult={() => setSection("application")} />}
        {section === "application" && <ClientResult appId={appId} draftRequest={draftRequest} onEditData={() => setSection("data")} />}
        {section === "fees" && <ClientFeeEstimate appId={appId} />}
        {section === "documents" && <ClientFilingPackage appId={appId} onEditData={() => setSection("data")} />}
        {section === "response" && <OfficeActionResponse appId={appId} />}
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
  const applicantDocumentInput = useRef<HTMLInputElement>(null);
  const [saving, setSaving] = useState(false);
  const [autoFilling, setAutoFilling] = useState(false);
  const [applicantDocumentUploading, setApplicantDocumentUploading] = useState(false);
  const [applicantDocuments, setApplicantDocuments] = useState<SourceDocumentDto[]>([]);
  const [imageUploading, setImageUploading] = useState(false);
  const [audioUploading, setAudioUploading] = useState(false);
  const [markAudio, setMarkAudio] = useState<SourceDocumentDto | null>(null);
  const [markImage, setMarkImage] = useState<MarkImageDto | null>(null);
  const [previewUrl, setPreviewUrl] = useState<string | null>(null);
  const [form, setForm] = useState({
    name: client?.fullNameOrCompanyName || "",
    inn: client?.inn || "",
    ogrn: client?.ogrnOrOgrnip || "",
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
  });

  const set = (key: keyof typeof form, value: string) => setForm((old) => ({ ...old, [key]: value }));
  const imageMark = form.markType === "figurative" || form.markType === "combined";
  const soundMark = form.markType === "sound";

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
      const changed = Object.values(values).filter((value) => Boolean(value?.trim())).length;
      setForm((current) => ({
        ...current,
        name: values.name?.trim() || current.name,
        inn: values.inn?.trim() || current.inn,
        ogrn: values.ogrn?.trim() || current.ogrn,
        address: values.address?.trim() || current.address,
        business: values.business_activity?.trim() || current.business,
      }));

      await loadApplicantDocuments();
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
    if (r > 170 && g > 120 && b < 100) return "оранжевый";
    if (r > 150 && b > 130 && g < 130) return "фиолетовый";
    if (r === max && g < 150) return "красный";
    if (g === max && b > 120) return "бирюзовый";
    if (g === max) return "зелёный";
    if (b === max && r < 100) return "синий";
    return hex.toUpperCase();
  };

  const generateAllDetails = async () => {
    setAutoFilling(true);
    try {
      await api.put(`/applications/${application.id}`, {
        mark_name: form.markName.trim(),
        mark_text: (form.markText || form.markName).trim(),
        mark_type: form.markType,
      });
      const language = await api.post<{ transliteration: string | null; translation: string | null }>(
        `/applications/${application.id}/suggest-mark-language`,
      );
      const extractedColors = Array.from(new Set((markImage?.dominant_colors || []).map(colorName)))
        .filter((value) => value !== "белый" || (markImage?.dominant_colors || []).length === 1)
        .slice(0, 4)
      const neutralColors = new Set(["чёрный", "белый", "серый", "светло-серый"]);
      const colorClaim = extractedColors.length > 0 && extractedColors.every((value) => neutralColors.has(value))
        ? ""
        : extractedColors.join(", ");
      setForm((current) => {
        const enriched = { ...current, colors: colorClaim };
        return {
          ...enriched,
          // Повторная автогенерация намеренно заменяет прежний шаблон: иначе
          // исправленное описание и актуальные цвета не попадут в заявление.
          description: buildDescription(enriched),
          // Для монохромного знака поле (591) оставляется пустым. Старое
          // противоречащее изображению значение намеренно заменяется.
          transliteration: current.transliteration.trim() || language.transliteration || "",
          translation: current.translation.trim() || language.translation || "",
        };
      });
      toast({ title: "Сведения подготовлены", description: "Проверьте предложения системы перед сохранением." });
    } catch (error) {
      generateDescription();
      toast({ title: "Описание подготовлено", description: "Перевод временно недоступен; остальные сведения можно проверить вручную." });
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
    loadApplicantDocuments()
      .catch(() => undefined);
  }, [application.id]);

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
      if (form.markType === "combined" && image.recognized_text.trim()) {
        set("markText", image.recognized_text.replace(/\s+/g, " ").trim());
      }
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

  const save = async () => {
    if (!form.name.trim() || !form.markName.trim()) {
      toast({ title: "Заполните обязательные поля", description: "Нужны заявитель и обозначение.", variant: "destructive" });
      return;
    }
    if (imageMark && !markImage) {
      toast({ title: "Загрузите изображение знака", description: "Оно обязательно для изобразительного и комбинированного обозначения.", variant: "destructive" });
      return;
    }
    if (soundMark && !markAudio) {
      toast({ title: "Загрузите аудиозапись знака", description: "Для звукового обозначения нужен файл MP3 или WAV.", variant: "destructive" });
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
          mark_name: form.markName.trim(),
          mark_text: form.markType === "figurative" ? "" : (form.markType === "combined" ? form.markText.trim() : form.markName.trim()),
          mark_type: form.markType,
          business_description: form.business.trim() || null, goods_services_raw: form.goods.trim() || null,
          description_of_mark: form.description.trim() || null, colors_claimed: form.colors.trim() || null,
          transliteration: form.transliteration.trim() || null, translation: form.translation.trim() || null,
          territory: COUNTRY_OPTIONS.find((item) => item.code === form.country)?.name || "Россия",
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
      <section className="mb-8 rounded-[1.3rem] border-2 border-[#0d9f9b]/25 bg-[#eef9f8] p-5 sm:p-6">
        <div className="flex flex-col gap-4 sm:flex-row sm:items-start sm:justify-between">
          <div className="max-w-2xl">
            <div className="flex items-center gap-3">
              <span className="flex h-10 w-10 shrink-0 items-center justify-center rounded-full bg-white text-[#0d9f9b]">
                <FileText className="h-5 w-5" />
              </span>
              <div>
                <h3 className="text-xl font-semibold text-[#11113f]">Загрузите документы заявителя</h3>
                <p className="mt-1 text-sm leading-relaxed text-[#5f6072]">
                  Выписка ЕГРЮЛ или ЕГРИП заполнит реквизиты ниже. Паспорт и другие документы сохранятся в заявке. Все найденные значения можно изменить до продолжения.
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
      </section>
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
                <span className="rounded-full bg-amber-100 px-2.5 py-1 text-[11px] font-bold text-amber-800">Обязательно</span>
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
                  <Label className="inline-flex items-center gap-1 text-sm font-semibold">Слова на логотипе <HelpTip text="Мы используем подтверждённые слова для поиска похожих названий. Исправьте ошибки распознавания и укажите все читаемые словесные элементы." /></Label>
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
              <Label className="inline-flex items-center gap-1 text-sm font-semibold">Аудиозапись обозначения <HelpTip text="Загрузите запись именно того звука, который хотите зарегистрировать. Рекомендуемый Роспатентом формат — MP3; поддерживается и WAV." /></Label>
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
          <MarkedField label="Чем вы занимаетесь" mode="manual"><Textarea rows={3} value={form.business} onChange={(e) => set("business", e.target.value)} placeholder="Например: производство одежды и продажа через интернет-магазин" /></MarkedField>
          <MarkedField label={<span className="inline-flex items-center gap-1">Товары и услуги <HelpTip text="Перечислите то, что вы продаёте или делаете под этим названием. Например: одежда, доставка еды, обучение, разработка программ. От этого зависит объём защиты знака." /></span>} mode="manual"><Textarea rows={3} value={form.goods} onChange={(e) => set("goods", e.target.value)} placeholder="Например: одежда, обувь, розничная торговля" /></MarkedField>
          <details className="rounded-xl border border-[#11113f]/10 bg-white p-4">
            <summary className="cursor-pointer font-semibold text-[#11113f]">Сведения о знаке для заявления</summary>
            <div className="mt-3 flex flex-wrap items-center justify-between gap-3"><p className="text-xs leading-relaxed text-[#6d6d7d]">Система заполнит применимые поля. Вам останется их проверить.</p><Button type="button" variant="outline" size="sm" disabled={autoFilling} onClick={() => void generateAllDetails()}>{autoFilling ? <Loader2 className="h-4 w-4 animate-spin" /> : <Sparkles className="h-4 w-4" />} Заполнить автоматически</Button></div>
            <div className="mt-4 space-y-4">
              <div><Label className="text-sm font-semibold">Описание обозначения</Label><Textarea className="mt-2" rows={3} value={form.description} onChange={(e) => set("description", e.target.value)} placeholder="Нажмите «Заполнить автоматически»" /></div>
              <div><Label className="text-sm font-semibold">Цвета</Label><Input className="mt-2" value={form.colors} onChange={(e) => set("colors", e.target.value)} placeholder="Определятся по изображению" /></div>
              <div className="grid gap-4 sm:grid-cols-2">
                <div><Label className="text-sm font-semibold">Написание латиницей</Label><Input className="mt-2" value={form.transliteration} onChange={(e) => set("transliteration", e.target.value)} placeholder="Определится автоматически" /></div>
                <div><Label className="text-sm font-semibold">Перевод</Label><Input className="mt-2" value={form.translation} onChange={(e) => set("translation", e.target.value)} placeholder="Останется пустым, если перевод не нужен" /></div>
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
  const [recalculatingClasses, setRecalculatingClasses] = useState(false);
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
    const [fields, classData] = await Promise.all([
      api.get<ReconciliationDto>(`/applications/${appId}/field-reconciliation`).catch(() => null),
      api.get<{ suggestions: ClassSuggestion[] }>(`/applications/${appId}/classes`).catch(() => ({ suggestions: [] })),
    ]);
    if (autoSuggest && classData.suggestions.length === 0) {
      await api.post(`/applications/${appId}/nice-classes/suggest`).catch(() => undefined);
      return load(false);
    }
    setReconciliation(fields); setClasses(classData.suggestions); setLoading(false);
  };
  useEffect(() => { void load(); }, [appId]);

  const decide = async (item: ClassSuggestion, approved: boolean) => {
    try { await api.put(`/applications/${appId}/classes/${item.id}/approve`, { suggestion_id: item.id, approved }); await load(); }
    catch (error) { toast({ title: "Не удалось сохранить выбор", description: messageOf(error, "Попробуйте ещё раз"), variant: "destructive" }); }
  };

  const recalculateClasses = async () => {
    setRecalculatingClasses(true);
    try {
      const result = await api.post<{
        status: string;
        suggestions?: unknown[];
      }>(`/applications/${appId}/nice-classes/suggest?replace_all=true`);
      await load(false);
      toast({
        title: "Классы подобраны заново",
        description: `Прежний список заменён. По актуальным данным предложено классов: ${result.suggestions?.length || 0}.`,
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
          <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
            <h3 className="inline-flex items-center gap-1 text-xl font-semibold">Классы товаров и услуг <HelpTip text="МКТУ — международный справочник из 45 классов. Классы 1–34 относятся к товарам, 35–45 — к услугам. Знак защищается не вообще, а только для выбранных товаров и услуг." /></h3>
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
          <p className="mt-2 rounded-lg bg-[#f8f7f4] px-3 py-2 text-xs leading-relaxed text-[#5f6072]">
            Изменили документы, описание бизнеса или перечень товаров? Нажмите «Подобрать заново». Прежние классы будут удалены, а список сформируется заново по актуальным данным.
          </p>
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
  // Уже установленный высокий риск важнее технической незавершённости
  // другой части проверки. Иначе экран одновременно советовал не подавать
  // знак, но прятал основание под заголовком «проверку нужно завершить».
  const presentation = risk ? {
    low: { title: "Можно продолжать", tone: "border-emerald-200 bg-emerald-50", icon: ShieldCheck, color: "text-emerald-700" },
    medium: { title: "Продолжайте с осторожностью", tone: "border-amber-200 bg-amber-50", icon: ShieldAlert, color: "text-amber-700" },
    high: { title: "Сначала доработайте знак", tone: "border-orange-200 bg-orange-50", icon: ShieldAlert, color: "text-orange-700" },
    critical: { title: "Подача не рекомендуется", tone: "border-red-200 bg-red-50", icon: AlertCircle, color: "text-red-700" },
  }[risk] : incomplete
    ? { title: "Проверку нужно завершить", tone: "border-amber-200 bg-amber-50", icon: ShieldAlert, color: "text-amber-700" }
    : null;

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
  const visibleRiskFindings = adverseFindings.slice(0, 3);
  const fallbackRisks = adverseFindings.length === 0 && !incomplete && risk && risk !== "low"
    ? (memo?.key_risks_json || []).slice(0, 3)
    : [];
  const hasVisibleRisks = visibleRiskFindings.length > 0 || fallbackRisks.length > 0;
  const friendlyIncomplete = (value: string) => {
    const normalized = value.toLocaleLowerCase("ru-RU");
    if (normalized.includes("абсолют") || normalized.includes("подтверждённых данных")) {
      return "Не завершена проверка графических элементов изображения по требованиям статьи 1483. Поиск похожих знаков в выбранных классах уже выполнен.";
    }
    if (normalized.includes("относитель") || normalized.includes("сходных")) {
      return "Не завершён поиск похожих товарных знаков в реестре.";
    }
    if (normalized.includes("мкту") || normalized.includes("класс")) {
      return "Нужно подтвердить выбранные классы товаров и услуг.";
    }
    return `Не завершена проверка: ${value}`;
  };
  const shortFinding = (item: RiskFindingSummary) => {
    const record = item.verification?.registry_record;
    if (record?.mark_text) {
      const selected = new Set(classes.filter((entry) => entry.approved !== false).map((entry) => entry.class_number));
      const overlap = (record.classes || []).filter((value) => selected.has(Number(value)));
      return `Похожий знак «${record.mark_text}»${overlap.length ? ` найден в ваших классах: ${overlap.join(", ")}` : " требует дополнительной проверки"}.`;
    }
    const firstSentence = item.explanation.split(/(?<=[.!?])\s/)[0] || item.explanation;
    return firstSentence.length > 150 ? `${firstSentence.slice(0, 147)}…` : firstSentence;
  };
  const clientSummary = risk ? {
    low: "Серьёзных препятствий не найдено. Можно готовить заявку.",
    medium: "Есть моменты, которые лучше проверить перед подачей.",
    high: "Найдены существенные препятствия. Сначала лучше доработать знак.",
    critical: "В выбранных классах найдены опасные совпадения. Без изменений подавать заявку рискованно.",
  }[risk] : "Проверка выполнена не полностью. Завершите оставшийся шаг.";
  const selectedClassNumbers = new Set(classes.filter((item) => item.approved !== false).map((item) => item.class_number));
  const visualMatches = findings
    .filter((item) => item.verification?.image_comparison)
    .sort((left, right) => {
      const inSelectedClasses = (item: RiskFindingSummary) => (item.verification?.registry_record?.classes || [])
        .some((value) => selectedClassNumbers.has(Number(value)));
      return Number(inSelectedClasses(right)) - Number(inSelectedClasses(left))
        || (right.verification?.image_comparison?.score || 0) - (left.verification?.image_comparison?.score || 0);
    });
  const strongestVisualMatch = visualMatches.reduce((best, item) =>
    (item.verification?.image_comparison?.score || 0) > (best?.verification?.image_comparison?.score || 0) ? item : best,
  null as RiskFindingSummary | null);
  return (
    <ClientPanel title="Результат проверки" description="Главный вывод, выбранные классы и риски, которые важно учесть до подачи.">
      <section className={cn("rounded-[1.5rem] border p-6 sm:p-8", presentation.tone)}>
        <div className="flex flex-col gap-5 sm:flex-row sm:items-start sm:justify-between"><div className="flex items-start gap-4"><span className="flex h-12 w-12 shrink-0 items-center justify-center rounded-full bg-white"><ResultIcon className={cn("h-6 w-6", presentation.color)} /></span><div><p className="inline-flex items-center gap-1 text-xs font-bold uppercase tracking-[0.15em] text-[#6d6d7d]">Предварительный вывод <HelpTip text="Это автоматическая предварительная оценка. Окончательное решение принимает Роспатент." /></p><h3 className={cn("mt-1 text-3xl font-semibold", presentation.color)}>{presentation.title}</h3><p className="mt-3 max-w-3xl text-lg leading-relaxed text-[#11113f]">{clientSummary}</p></div></div><Button variant="outline" className="rounded-full bg-white" disabled={running} onClick={rerun}>{running && <Loader2 className="h-4 w-4 animate-spin" />} Обновить</Button></div>
      </section>
      {visualMatches.length > 0 && (
        <section className="mt-6 rounded-[1.3rem] border border-[#0d9f9b]/25 bg-[#edf9f8] p-5 sm:p-6">
          <div className="flex items-start gap-4">
            <span className="flex h-11 w-11 shrink-0 items-center justify-center rounded-full bg-white text-[#0d9f9b]"><ImageIcon className="h-5 w-5" /></span>
            <div>
              <h3 className="text-xl font-semibold">Изображение проанализировано</h3>
              <p className="mt-2 leading-relaxed text-[#55556f]">Сравнили {visualMatches.length} изображений.{strongestVisualMatch && <> Самое похожее — «{strongestVisualMatch.verification?.registry_record?.mark_text || "знак без названия"}», сходство <strong className="text-[#11113f]">{Math.round((strongestVisualMatch.verification?.image_comparison?.score || 0) * 100)}%</strong>.</>}</p>
            </div>
          </div>
        </section>
      )}
      <div className="mt-6 grid gap-5 lg:grid-cols-2">
        <section className="rounded-[1.3rem] border border-[#11113f]/10 p-5 sm:p-6"><h3 className="text-xl font-semibold">Что делать дальше</h3><p className="mt-3 leading-relaxed text-[#55556f]">{memo?.recommended_action ? ACTION_LABELS[memo.recommended_action] ?? "Проверьте результат перед подачей" : incomplete ? "Дождитесь завершения всех проверок и повторите анализ." : "Проверьте выбранные классы и переходите к подготовке заявления."}</p><div className="mt-5 flex flex-wrap gap-2">{classes.filter((item) => item.approved !== false).map((item) => <Badge key={item.id} className="bg-[#e8f7f6] text-[#087c78] hover:bg-[#e8f7f6]">МКТУ {item.class_number}</Badge>)}</div></section>
        <section className="rounded-[1.3rem] border border-[#11113f]/10 p-5 sm:p-6">
          <h3 className="text-xl font-semibold">{hasVisibleRisks ? "Главные риски" : incomplete ? "Что осталось проверить" : "Результат проверки"}</h3>
          <div className="mt-4 space-y-3">
            {visibleRiskFindings.map((item) => <div key={item.id} className="rounded-xl bg-[#f8f7f4] p-4"><div className="flex items-start gap-3 text-sm font-medium leading-relaxed text-[#11113f]"><span className="mt-2 h-2 w-2 shrink-0 rounded-full bg-[#ef5b62]" />{shortFinding(item)}</div><details className="mt-2 pl-5 text-sm text-[#6d6d7d]"><summary className="cursor-pointer text-[#0d8f8b]">Почему это важно</summary><p className="mt-2 leading-relaxed">{item.explanation}</p></details></div>)}
            {fallbackRisks.map((item, index) => <div key={index} className="flex items-start gap-3 text-sm leading-relaxed text-[#55556f]"><span className="mt-2 h-2 w-2 shrink-0 rounded-full bg-[#ef5b62]" />{item.split(/(?<=[.!?])\s/)[0]}</div>)}
            {!hasVisibleRisks && incompleteReasons.map((item, index) => <div key={index} className="flex items-start gap-3 text-sm leading-relaxed text-[#55556f]"><span className="mt-2 h-2 w-2 shrink-0 rounded-full bg-amber-500" />{friendlyIncomplete(item)}</div>)}
            {incomplete && incompleteReasons.length === 0 && !hasVisibleRisks && <p className="text-sm text-[#6d6d7d]">Одна часть проверки пока не завершена.</p>}
            {!incomplete && !hasVisibleRisks && <div className="flex items-start gap-3 rounded-xl bg-emerald-50 p-4 text-emerald-900"><CheckCircle2 className="mt-0.5 h-5 w-5 shrink-0" /><p className="text-sm leading-relaxed">Серьёзных препятствий не найдено.</p></div>}
          </div>
        </section>
      </div>
      {incomplete && hasVisibleRisks && (
        <section className="mt-5 rounded-[1.2rem] border border-amber-200 bg-amber-50 p-5">
          <h3 className="font-semibold text-amber-900">Что ещё требует проверки</h3>
          <div className="mt-3 space-y-2">{incompleteReasons.map((item, index) => <div key={index} className="flex items-start gap-3 text-sm text-amber-900/80"><span className="mt-2 h-2 w-2 shrink-0 rounded-full bg-amber-500" />{friendlyIncomplete(item)}</div>)}</div>
        </section>
      )}
      {visualMatches.length > 0 && (
        <section className="mt-6 rounded-[1.3rem] border border-[#11113f]/10 p-5 sm:p-6">
          <h3 className="text-xl font-semibold">Похожие изображения</h3>
          <p className="mt-2 text-sm text-[#6d6d7d]">Сначала показываем самые похожие знаки из выбранных классов.</p>
          <div className="mt-5 grid gap-4 lg:grid-cols-2">
            {visualMatches.slice(0, 3).map((finding) => <ClientVisualMatch key={finding.id} appId={appId} finding={finding} />)}
          </div>
          {visualMatches.length > 3 && <details className="mt-5"><summary className="cursor-pointer font-semibold text-[#0d8f8b]">Показать ещё {visualMatches.length - 3}</summary><div className="mt-4 grid gap-4 lg:grid-cols-2">{visualMatches.slice(3).map((finding) => <ClientVisualMatch key={finding.id} appId={appId} finding={finding} />)}</div></details>}
        </section>
      )}
      <ClientDraftPreview appId={appId} analysisComplete={!incomplete} openRequest={draftRequest} onEditData={onEditData} />
      <p className="mt-6 text-sm leading-relaxed text-[#6d6d7d]">Результат сформирован автоматически на основе введённых данных, выбранных классов и доступных реестров. Он помогает принять решение, но не является гарантией регистрации или юридической консультацией.</p>
    </ClientPanel>
  );
}

function ClientVisualMatch({ appId, finding }: { appId: number; finding: RiskFindingSummary }) {
  const comparison = finding.verification?.image_comparison;
  const record = finding.verification?.registry_record;
  return (
    <article className="rounded-2xl border border-[#11113f]/10 bg-[#f8f7f4] p-4">
      <div className="grid grid-cols-2 gap-3">
        <ProtectedImage path={`/applications/${appId}/mark-image/content`} label="Ваш знак" />
        <ProtectedImage path={`/risk-findings/${finding.id}/registry-image`} label="Найденный знак" />
      </div>
      <div className="mt-3 flex items-start justify-between gap-3">
        <div><p className="font-semibold text-[#11113f]">{record?.mark_text || "Знак без словесного элемента"}</p><p className="mt-1 text-xs text-[#6d6d7d]">МКТУ {(record?.classes || []).join(", ") || "не указаны"}</p></div>
        <span className="rounded-full bg-amber-100 px-3 py-1 text-sm font-bold text-amber-800">{Math.round((comparison?.score || 0) * 100)}%</span>
      </div>
    </article>
  );
}

function ProtectedImage({ path, label }: { path: string; label: string }) {
  const [url, setUrl] = useState<string | null>(null);
  useEffect(() => {
    let active = true;
    let objectUrl: string | null = null;
    api.blob(path).then((blob) => {
      if (!active) return;
      objectUrl = URL.createObjectURL(blob);
      setUrl(objectUrl);
    }).catch(() => undefined);
    return () => { active = false; if (objectUrl) URL.revokeObjectURL(objectUrl); };
  }, [path]);
  return <div><p className="mb-1 text-[11px] font-semibold text-[#6d6d7d]">{label}</p><div className="flex h-32 items-center justify-center rounded-xl border border-[#11113f]/10 bg-white p-2">{url ? <img src={url} alt={label} className="max-h-full max-w-full object-contain" /> : <span className="text-xs text-[#6d6d7d]">Нет изображения</span>}</div></div>;
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
  const [benefitOpen, setBenefitOpen] = useState(false);
  const [benefit, setBenefit] = useState("individual");
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
        <div className="mt-5 rounded-xl border border-[#11113f]/10 p-4">
          <div className="flex flex-wrap items-center justify-between gap-3"><div><p className="font-semibold text-[#11113f]">Есть право на льготу?</p><p className="mt-1 text-xs text-[#6d6d7d]">Проверим основание, не уменьшая сумму без подтверждающего документа.</p></div><Button type="button" variant="outline" onClick={() => setBenefitOpen((value) => !value)}>Проверить льготу</Button></div>
          {benefitOpen && <div className="mt-4 space-y-3"><Select value={benefit} onValueChange={setBenefit}><SelectTrigger><SelectValue /></SelectTrigger><SelectContent><SelectItem value="individual">Физлицо или самозанятый</SelectItem><SelectItem value="entrepreneur">ИП или субъект МСП</SelectItem><SelectItem value="public">Государственный орган из п. 13¹ Положения</SelectItem><SelectItem value="other">Иное специальное основание</SelectItem></SelectContent></Select><div className="rounded-lg bg-amber-50 p-3 text-xs leading-relaxed text-amber-900">{benefit === "public" ? "Возможное освобождение требует проверки статуса заявителя и подтверждающих документов. Сумма не изменена автоматически." : "Сам статус физлица, самозанятого, ИП или МСП не даёт общей скидки на обычную российскую заявку на товарный знак. Если у вас есть специальное основание, выберите «Иное» и передайте подтверждающий документ специалисту."}</div></div>}
        </div>
        <div className="mt-4 rounded-xl bg-amber-50 p-4 text-xs leading-relaxed text-amber-900">{fees.data.warnings.map((warning) => <p key={warning}>• {warning}</p>)}</div>
        <a href={fees.data.source_url} target="_blank" rel="noreferrer" className="mt-4 inline-block text-xs font-semibold text-[#087c78] underline underline-offset-4">Официальная таблица пошлин Роспатента ↗</a>
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
  filing_document_count: number;
  reference_document_count: number;
  class_numbers: number[];
  overall_risk: string | null;
  filing_fee: number | null;
  registration_fee: number | null;
  total_fee: number | null;
}

function ClientFilingPackage({ appId, onEditData }: { appId: number; onEditData: () => void }) {
  const pack = useApi<FilingPackageStatus>(`/applications/${appId}/filing-package`);
  const [downloading, setDownloading] = useState(false);
  const { toast } = useToast();

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
              {pack.data.blockers.some((item) => item.section === "data") && (
                <Button variant="outline" className="mt-4 rounded-full bg-white" onClick={onEditData}><PencilLine className="h-4 w-4" /> Перейти к данным</Button>
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

          {pack.data.warnings.length > 0 && <details className="mt-5 rounded-xl bg-[#f8f7f4] p-4 text-xs text-[#55556f]"><summary className="cursor-pointer font-semibold text-[#11113f]">Важные примечания ({pack.data.warnings.length})</summary><div className="mt-3 space-y-2 leading-relaxed">{pack.data.warnings.map((warning) => <p key={warning}>• {warning}</p>)}</div></details>}
        </div>
      )}
    </section>
  );
}
