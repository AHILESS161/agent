/**
 * Приём обращения от клиента.
 *
 * Поток построен «от документа»: юрист сначала прикладывает то, что
 * прислал клиент (выписку ЕГРЮЛ/ЕГРИП), система детерминированно
 * извлекает реквизиты и предзаполняет форму, а юрист проверяет и
 * правит. Ни одно значение не подставляется как подтверждённое —
 * это предзаполнение, а не ввод за специалиста.
 *
 * Приложенные документы после создания дела загружаются в него и
 * проходят то же извлечение, что и раньше: на вкладке «Сверка полей»
 * юрист подтверждает каждое поле перед попаданием в заявление.
 */

import { useEffect, useRef, useState } from "react";
import { useLocation } from "wouter";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import { Checkbox } from "@/components/ui/checkbox";
import { Badge } from "@/components/ui/badge";
import { Separator } from "@/components/ui/separator";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { useToast } from "@/hooks/use-toast";
import { api, ApiError, DOCUMENT_KIND_LABELS } from "@/lib/api";
import { useCases } from "@/lib/use-cases";
import { useAuth } from "@/lib/auth";
import { HelpTip } from "@/components/help-tip";
import { MARK_TYPE_LABELS, type MarkType } from "@shared/schema";
import { cn } from "@/lib/utils";
import {
  AlertCircle,
  ArrowRight,
  CheckCircle2,
  FileText,
  ImageIcon,
  Inbox,
  Loader2,
  Sparkles,
  Trash2,
  Upload,
} from "lucide-react";

const ACCEPTED = ".pdf,.docx,.txt,.png,.jpg,.jpeg,.mp3,.wav";

type ClientType = "company" | "sole_proprietor" | "individual";

const CLIENT_TYPE_LABELS: Record<ClientType, string> = {
  company: "Юридическое лицо",
  sole_proprietor: "Индивидуальный предприниматель",
  individual: "Физическое лицо / самозанятый",
};

// Как называется главный идентификатор у каждого типа заявителя.
const ID_LABEL: Record<ClientType, string> = {
  company: "ОГРН",
  sole_proprietor: "ОГРНИП",
  individual: "—",
};

interface PrefillResponse {
  document_kind: string | null;
  kind_confidence?: number | null;
  client_type: ClientType | null;
  prefill: {
    name?: string;
    short_name?: string;
    inn?: string;
    ogrn?: string;
    kpp?: string;
    address?: string;
    business_activity?: string;
  };
  fields: {
    field_id: string;
    label: string;
    value: string;
    confidence: number | null;
    is_sensitive: boolean;
    form_target: string | null;
  }[];
  warning: string | null;
  notice: string;
}

interface Attached {
  file: File;
  documentKind: string | null;
  autofilled: boolean;
  warning: string | null;
}

export default function IntakePage() {
  const { toast } = useToast();
  const { user, refreshProfile } = useAuth();
  const [, setLocation] = useLocation();
  const fileInput = useRef<HTMLInputElement>(null);
  const cases = useCases();

  // Документы клиента.
  const [attached, setAttached] = useState<Attached[]>([]);
  const [isReading, setIsReading] = useState(false);

  // Заявитель.
  const [useExistingClient, setUseExistingClient] = useState(false);
  const [clientId, setClientId] = useState<string>("");
  const [clientType, setClientType] = useState<ClientType>("company");
  const [name, setName] = useState("");
  const [inn, setInn] = useState("");
  const [ogrn, setOgrn] = useState("");
  const [kpp, setKpp] = useState("");
  const [address, setAddress] = useState("");
  const [contactEmail, setContactEmail] = useState("");
  const [contactPhone, setContactPhone] = useState("");
  const [rememberApplicantData, setRememberApplicantData] = useState(false);

  // Обозначение и деятельность.
  const [markName, setMarkName] = useState("");
  const [markType, setMarkType] = useState<MarkType>("word");
  const [businessDescription, setBusinessDescription] = useState("");
  const [goodsServices, setGoodsServices] = useState("");
  const [markImageFile, setMarkImageFile] = useState<File | null>(null);
  const [markImagePreview, setMarkImagePreview] = useState<string | null>(null);
  const [isInspectingImage, setIsInspectingImage] = useState(false);

  // Обращение (необязательное).
  const [sender, setSender] = useState("");
  const [bodyText, setBodyText] = useState("");

  const [isSaving, setIsSaving] = useState(false);
  const [caseId, setCaseId] = useState<number | null>(null);
  // Ключ идемпотентности на одно заполнение формы: повторный клик
  // не создаст дубль, а следующее дело получит новый ключ.
  const [submissionKey] = useState(() => crypto.randomUUID());

  const draftKey = `registr:intake-draft:${user?.id ?? "guest"}`;
  const saveDraft = (showNotice = false) => {
    localStorage.setItem(draftKey, JSON.stringify({
      useExistingClient, clientId, clientType, name, inn, ogrn, kpp, address, contactEmail, contactPhone,
      markName, markType, businessDescription, goodsServices, sender, bodyText,
    }));
    if (showNotice) toast({ title: "Черновик сохранён", description: "Текстовые поля сохранятся в этом браузере. Файлы после перезагрузки нужно выбрать заново." });
  };

  useEffect(() => {
    const raw = localStorage.getItem(draftKey);
    if (!raw) {
      const profile = user?.applicantProfile;
      if (profile) {
        setClientType(profile.type);
        setName(profile.fullNameOrCompanyName || "");
        setInn(profile.inn || "");
        setOgrn(profile.ogrnOrOgrnip || "");
        setKpp(profile.kpp || "");
        setAddress(profile.address || "");
        setContactEmail(profile.email || user?.email || "");
        setContactPhone(profile.phone || "");
      }
      return;
    }
    try {
      const draft = JSON.parse(raw);
      setUseExistingClient(Boolean(draft.useExistingClient));
      setClientId(draft.clientId || "");
      setClientType(draft.clientType || "company");
      setName(draft.name || "");
      setInn(draft.inn || "");
      setOgrn(draft.ogrn || "");
      setKpp(draft.kpp || "");
      setAddress(draft.address || "");
      setContactEmail(draft.contactEmail || "");
      setContactPhone(draft.contactPhone || "");
      setMarkName(draft.markName || "");
      setMarkType(draft.markType || "word");
      setBusinessDescription(draft.businessDescription || "");
      setGoodsServices(draft.goodsServices || "");
      setSender(draft.sender || "");
      setBodyText(draft.bodyText || "");
    } catch { localStorage.removeItem(draftKey); }
  }, [draftKey, user]);

  useEffect(() => {
    const timer = window.setTimeout(() => saveDraft(false), 500);
    return () => window.clearTimeout(timer);
  }, [useExistingClient, clientId, clientType, name, inn, ogrn, kpp, address, contactEmail, contactPhone, markName, markType, businessDescription, goodsServices, sender, bodyText]);

  const clients = Object.values(cases.data?.clientsById ?? {});
  const clientPortal = user?.role === "client";
  const clientActivity = goodsServices || businessDescription;
  const imageMark = markType === "figurative" || markType === "combined";

  useEffect(() => {
    if (!markImageFile) {
      setMarkImagePreview(null);
      return;
    }
    const url = URL.createObjectURL(markImageFile);
    setMarkImagePreview(url);
    return () => URL.revokeObjectURL(url);
  }, [markImageFile]);

  const chooseMarkImage = async (file: File | null, inferMarkType = false) => {
    setMarkImageFile(file);
    if (!file) return;
    setIsInspectingImage(true);
    try {
      const inspected = await api.upload<{ recognized_text?: string | null }>("/mark-images/inspect", file);
      const recognized = (inspected.recognized_text || "").replace(/\s+/g, " ").trim();
      if (inferMarkType && markType === "word") {
        setMarkType(recognized ? "combined" : "figurative");
      }
      if (recognized && !markName.trim()) {
        setMarkName(recognized.slice(0, 300));
        toast({ title: "Текст на изображении распознан", description: "Мы подставили его в поле обозначения. Обязательно сверьте написание с картинкой." });
      } else if (!recognized) {
        toast({ title: "Изображение загружено", description: "Текст не распознан — обозначение можно указать вручную." });
      }
    } catch (error) {
      toast({ title: "Не удалось прочитать изображение", description: error instanceof ApiError ? error.message : "Проверьте формат файла", variant: "destructive" });
    } finally {
      setIsInspectingImage(false);
    }
  };

  // Заполнить поле, только если оно ещё пустое: правки юриста важнее
  // предзаполнения и не должны затираться следующим документом.
  const fillIfEmpty = (
    setter: (v: string) => void,
    current: string,
    value?: string,
  ) => {
    if (value && !current.trim()) setter(value);
  };

  const readDocument = async (file: File) => {
    const extension = file.name.toLowerCase().split(".").pop();
    if (extension === "mp3" || extension === "wav") {
      setAttached((prev) => [...prev, { file, documentKind: "mark_audio", autofilled: false, warning: null }]);
      if (fileInput.current) fileInput.current.value = "";
      return;
    }
    if ((extension === "png" || extension === "jpg" || extension === "jpeg") && (markType === "figurative" || markType === "combined")) {
      await chooseMarkImage(file);
      if (fileInput.current) fileInput.current.value = "";
      return;
    }
    setIsReading(true);
    try {
      const result = await api.upload<PrefillResponse>(
        "/intake/prefill-registrant",
        file,
      );

      if (result.document_kind === "mark_image") {
        await chooseMarkImage(file, true);
        toast({ title: "Изображение знака добавлено", description: "Мы определили вид знака и попробовали распознать заявляемое обозначение." });
        return;
      }

      const filled = Object.keys(result.prefill).length > 0;
      if (result.client_type) setClientType(result.client_type);
      fillIfEmpty(setName, name, result.prefill.name);
      fillIfEmpty(setInn, inn, result.prefill.inn);
      fillIfEmpty(setOgrn, ogrn, result.prefill.ogrn);
      fillIfEmpty(setAddress, address, result.prefill.address);
      fillIfEmpty(
        setBusinessDescription,
        businessDescription,
        result.prefill.business_activity,
      );

      setAttached((prev) => [
        ...prev,
        {
          file,
          documentKind: result.document_kind,
          autofilled: filled,
          warning: result.warning,
        },
      ]);

      if (filled) {
        // Новый документ — данные заявителя, значит клиент новый.
        setUseExistingClient(false);
        toast({
          title: "Данные подставлены в форму",
          description:
            "Проверьте их по документу и при необходимости поправьте — " +
            "ничего пока не подтверждено.",
        });
      } else if (result.warning) {
        toast({
          title: "Документ приложен",
          description: result.warning,
        });
      } else {
        toast({
          title: "Документ приложен",
          description: `${DOCUMENT_KIND_LABELS[result.document_kind ?? ""] ?? "Документ"} — реквизиты не извлечены.`,
        });
      }
    } catch (e) {
      toast({
        title: "Не удалось прочитать документ",
        description: e instanceof ApiError ? e.message : "Неизвестная ошибка",
        variant: "destructive",
      });
    } finally {
      setIsReading(false);
      if (fileInput.current) fileInput.current.value = "";
    }
  };

  const removeAttachment = (index: number) => {
    setAttached((prev) => prev.filter((_, i) => i !== index));
  };

  const setAttachmentKind = (index: number, documentKind: string) => {
    if (documentKind === "mark_image") {
      const file = attached[index]?.file;
      if (file) void chooseMarkImage(file);
      removeAttachment(index);
      return;
    }
    setAttached((prev) => prev.map((item, i) => i === index ? { ...item, documentKind } : item));
  };

  const validate = (): string | null => {
    if (useExistingClient) {
      if (!clientId) return "Выберите клиента или заполните данные нового.";
    } else if (name.trim().length < 2) {
      return "Укажите наименование или ФИО заявителя.";
    }
    if (!markName.trim()) return "Укажите заявляемое обозначение.";
    if (imageMark && !markImageFile) {
      return "Добавьте изображение товарного знака в формате PNG или JPEG.";
    }
    return null;
  };

  const submit = async () => {
    const problem = validate();
    if (problem) {
      toast({ title: "Проверьте форму", description: problem, variant: "destructive" });
      return;
    }

    setIsSaving(true);
    try {
      // 1. Регистрируем обращение и создаём дело.
      const event = await api.post<{
        id: number;
        created_case_id: number | null;
        target_case_id: number | null;
      }>("/inbound/events", {
        idempotency_key: submissionKey,
        sender: sender || null,
        body_text: bodyText || null,
        create_case: true,
        client_id: useExistingClient ? Number(clientId) : null,
        new_client: useExistingClient
          ? null
          : {
              type: clientType,
              full_name_or_company_name: name.trim(),
              inn: inn.trim() || null,
              ogrn_or_ogrnip: ogrn.trim() || null,
              kpp: kpp.trim() || null,
              address: address.trim() || null,
              country: "RU",
              email: contactEmail.trim() || null,
              phone: contactPhone.trim() || null,
            },
        mark_name: markName.trim() || null,
        mark_text: markName.trim() || null,
        mark_type: markType,
        business_description: (clientPortal ? clientActivity : businessDescription).trim() || null,
        goods_services: (clientPortal ? clientActivity : goodsServices).trim() || null,
        description_of_mark: null,
      });

      const newCaseId = event.created_case_id ?? event.target_case_id;
      if (!newCaseId) {
        throw new ApiError(500, "Дело не создано");
      }

      // 2. Загружаем приложенные документы в дело и извлекаем реквизиты.
      //    Так документ оказывается в деле, а поля — на вкладке «Сверка».
      let uploaded = 0;
      let markImageUploadFailed = false;
      if (imageMark && markImageFile) {
        try {
          const uploadedImage = await api.upload<{ recognized_text?: string | null }>(`/applications/${newCaseId}/mark-image`, markImageFile);
          uploaded += 1;
          const recognized = (uploadedImage.recognized_text || "").replace(/\s+/g, " ").trim();
          const effectiveMarkName = markName.trim() || recognized;
          if (effectiveMarkName && effectiveMarkName !== markName.trim()) {
            await api.put(`/applications/${newCaseId}`, { mark_name: effectiveMarkName, mark_text: effectiveMarkName });
          }
          try {
            const details = await api.post<{ description: string; colors: string[]; transliteration?: string; translation?: string }>(`/applications/${newCaseId}/generate-mark-description`);
            await api.put(`/applications/${newCaseId}`, {
              description_of_mark: details.description,
              colors_claimed: details.colors.join(", "),
              transliteration: details.transliteration || null,
              translation: details.translation || null,
            });
            await api.post(`/applications/${newCaseId}/mark-details-suggestions`, {
              description_of_mark: details.description,
              colors_claimed: details.colors.join(", "),
              transliteration: details.transliteration || null,
              translation: details.translation || null,
            });
          } catch {
            // Заявка и изображение уже сохранены. На экране проверки остаётся
            // отдельная понятная кнопка повторной подготовки описания.
          }
        } catch {
          markImageUploadFailed = true;
        }
      }
      for (const item of attached) {
        // Отдельно выбранное изображение имеет приоритет над файлом,
        // ранее помеченным как изображение в общем списке документов.
        if (markImageFile && item.documentKind === "mark_image") continue;
        try {
          const endpoint = item.documentKind === "mark_image"
            ? `/applications/${newCaseId}/mark-image`
            : `/applications/${newCaseId}/source-documents`;
          const doc = await api.upload<{ id?: number; document_id?: number; processing_status?: string }>(
            endpoint,
            item.file,
          );
          uploaded += 1;
          // Извлечение имеет смысл только для распознанных выписок.
          const documentId = doc.id ?? doc.document_id;
          if (documentId && item.documentKind === "passport") {
            await api.put(`/source-documents/${documentId}/kind`, { document_kind: "passport" });
          }
          if (documentId && doc.processing_status === "extracted" && item.documentKind !== "mark_image") {
            await api.post(`/source-documents/${documentId}/extract`).catch(() => {
              // Для типов без правил извлечения — это норма, не ошибка.
            });
          }
        } catch {
          // Один сбойный файл не должен ронять создание дела.
        }
      }

      let profileSaveFailed = false;
      if (clientPortal && !useExistingClient && rememberApplicantData) {
        try {
          await api.patch("/auth/me", {
            applicant_profile_json: {
              type: clientType,
              full_name_or_company_name: name.trim() || null,
              inn: inn.trim() || null,
              ogrn_or_ogrnip: ogrn.trim() || null,
              kpp: kpp.trim() || null,
              address: address.trim() || null,
              country: "RU",
              email: contactEmail.trim() || null,
              phone: contactPhone.trim() || null,
            },
          });
          await refreshProfile();
        } catch {
          // Заявка уже создана: ошибка профиля не должна отменять результат.
          profileSaveFailed = true;
        }
      }

      setCaseId(newCaseId);
      localStorage.removeItem(draftKey);
      toast({
        title: clientPortal ? `Заявка №${newCaseId} создана` : `Дело №${newCaseId} создано`,
        description: profileSaveFailed
          ? "Заявка создана, но сохранить реквизиты в профиль не удалось. Это можно повторить на экране проверки данных."
          : markImageUploadFailed
          ? "Заявка сохранена, но изображение не загрузилось. Добавьте его ещё раз на экране «Данные»."
          : uploaded
          ? `Документов приложено: ${uploaded}. Реквизиты ждут проверки на этапе «Данные».`
          : "Документы не приложены — их можно добавить в карточке дела.",
        variant: markImageUploadFailed || profileSaveFailed ? "destructive" : undefined,
      });
    } catch (e) {
      toast({
        title: "Не удалось создать дело",
        description: e instanceof ApiError ? e.message : "Неизвестная ошибка",
        variant: "destructive",
      });
    } finally {
      setIsSaving(false);
    }
  };

  if (caseId) {
    return (
      <div className="max-w-3xl space-y-4" data-testid="intake-done">
        <Card className="border-primary/40">
          <CardContent className="p-4 flex items-center justify-between gap-3">
            <div className="flex items-center gap-3">
              <CheckCircle2 className="w-6 h-6 text-emerald-600" />
              <div>
                <p className="text-sm font-medium">{clientPortal ? `Заявка №${caseId} создана` : `Дело №${caseId} создано`}</p>
                <p className="text-xs text-muted-foreground">
                  Дальше проверьте данные и добавьте недостающие документы.
                </p>
              </div>
            </div>
            <Button size="sm" onClick={() => setLocation(`/applications/${caseId}`)}>
              Открыть заявку
              <ArrowRight className="w-3.5 h-3.5 ml-1.5" />
            </Button>
          </CardContent>
        </Card>
      </div>
    );
  }

  return (
    <div className="mx-auto max-w-6xl space-y-8" data-testid="intake-page">
      <div className="flex flex-col justify-between gap-5 border-b border-border pb-7 sm:flex-row sm:items-end">
        <div>
          <p className="mb-2 text-sm font-semibold uppercase tracking-[0.14em] text-primary">Новый товарный знак</p>
          <h1 className="text-4xl font-semibold sm:text-5xl">{clientPortal ? "Начнём с главного" : "Создание проекта"}</h1>
          <p className="mt-3 max-w-2xl text-base leading-relaxed text-muted-foreground">
            {clientPortal
              ? "Добавьте документ или заполните короткую форму. Всё можно сохранить и дополнить позже."
              : "Три шага: документы, заявитель и обозначение. Все данные можно изменить позже."}
          </p>
        </div>
        <div className="hidden items-center gap-2 text-sm text-muted-foreground sm:flex">
          <span className="h-2.5 w-2.5 rounded-full bg-primary" />
          Автосохранение после создания
        </div>
      </div>

      {/* Шаг 1: документы (первым — с них начинается работа) */}
      <ProjectStep
        n={1}
        title="Добавьте документы"
        description="Необязательно. Добавьте выписку ЕГРЮЛ/ЕГРИП, паспорт физлица, изображение или аудиозапись знака."
      >
          <div
            className="flex flex-col items-center gap-3 rounded-xl border-2 border-dashed border-primary/35 bg-primary/[0.035] px-6 py-9 text-center transition-colors hover:border-primary/60 hover:bg-primary/[0.055]"
            data-testid="intake-dropzone"
          >
            <span className="flex h-12 w-12 items-center justify-center rounded-full bg-primary/10 text-primary">
              <Upload className="h-6 w-6" />
            </span>
            <Button
              variant="default"
              disabled={isReading}
              onClick={() => fileInput.current?.click()}
              data-testid="button-attach"
            >
              {isReading ? (
                <Loader2 className="w-3.5 h-3.5 mr-1.5 animate-spin" />
              ) : (
                <Upload className="w-3.5 h-3.5 mr-1.5" />
              )}
              {isReading ? "Читаем документ…" : "Выбрать документ"}
            </Button>
            <p className="text-sm text-muted-foreground">
              PDF, DOCX, TXT, PNG, JPG, MP3 или WAV · до 25 МБ
            </p>
          </div>
          <input
            ref={fileInput}
            type="file"
            accept={ACCEPTED}
            className="hidden"
            data-testid="input-attachment"
            onChange={(e) => {
              const file = e.target.files?.[0];
              if (file) void readDocument(file);
            }}
          />

          {attached.length > 0 && (
            <div className="mt-5 space-y-2">
              {attached.map((item, index) => (
                <div
                  key={`${item.file.name}-${index}`}
                  className="flex items-start gap-3 rounded-lg border border-border bg-background px-4 py-3"
                >
                  <FileText className="w-4 h-4 shrink-0 mt-0.5 text-muted-foreground" />
                  <div className="min-w-0 flex-1">
                    <p className="truncate text-sm font-semibold">{item.file.name}</p>
                    <p className="text-xs text-muted-foreground">
                      {DOCUMENT_KIND_LABELS[item.documentKind ?? ""] ??
                        "Тип не определён"}
                    </p>
                    {item.warning && (
                      <p className="mt-1 flex items-start gap-1 text-xs text-amber-600 dark:text-amber-500">
                        <AlertCircle className="w-3 h-3 mt-0.5 shrink-0" />
                        {item.warning}
                      </p>
                    )}
                    {/\.(png|jpe?g)$/i.test(item.file.name) && (
                      <div className="mt-2 flex flex-wrap gap-2">
                        <button type="button" onClick={() => setAttachmentKind(index, "mark_image")} className={cn("rounded-full border px-2.5 py-1 text-[11px] font-semibold", item.documentKind === "mark_image" ? "border-primary bg-primary/10 text-primary" : "border-border")}>Это изображение знака</button>
                        <button type="button" onClick={() => setAttachmentKind(index, clientType === "individual" ? "passport" : "other")} className={cn("rounded-full border px-2.5 py-1 text-[11px] font-semibold", item.documentKind !== "mark_image" ? "border-primary bg-primary/10 text-primary" : "border-border")}>Это документ заявителя</button>
                      </div>
                    )}
                  </div>
                  {item.autofilled && (
                    <Badge className="shrink-0 bg-emerald-500/15 text-emerald-700 dark:text-emerald-400">
                      <Sparkles className="w-3 h-3 mr-1" />
                      данные в форме
                    </Badge>
                  )}
                  <button
                    type="button"
                    className="shrink-0 text-xs text-muted-foreground hover:text-destructive"
                    onClick={() => removeAttachment(index)}
                    data-testid={`remove-attachment-${index}`}
                  >
                    убрать
                  </button>
                </div>
              ))}
            </div>
          )}
      </ProjectStep>

      {/* Шаг 2: заявитель */}
      <ProjectStep
        n={2}
        title="Укажите заявителя"
        description="Создайте нового заявителя или выберите существующего из базы."
      >
          {!clientPortal && <div className="inline-flex rounded-lg bg-muted p-1">
            <button
              type="button"
              className={cn(
                "rounded-md px-5 py-2.5 text-sm font-semibold transition-all",
                !useExistingClient ? "bg-card text-foreground shadow-sm" : "text-muted-foreground hover:text-foreground",
              )}
              onClick={() => setUseExistingClient(false)}
            >
              Новый заявитель
            </button>
            <button
              type="button"
              className={cn(
                "rounded-md px-5 py-2.5 text-sm font-semibold transition-all",
                useExistingClient ? "bg-card text-foreground shadow-sm" : "text-muted-foreground hover:text-foreground",
              )}
              onClick={() => setUseExistingClient(true)}
            >
              Выбрать из базы
            </button>
          </div>}

          {useExistingClient ? (
            <div className="mt-6">
            <Field label="Заявитель">
              <Select value={clientId} onValueChange={setClientId}>
                <SelectTrigger data-testid="select-client">
                  <SelectValue placeholder="Начните вводить название" />
                </SelectTrigger>
                <SelectContent>
                  {clients.map((client) => (
                    <SelectItem key={client.id} value={String(client.id)}>
                      {client.shortName}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </Field>
            </div>
          ) : (
            <div className="mt-6 grid gap-5">
              <Field label="Тип заявителя">
                <Select
                  value={clientType}
                  onValueChange={(v) => setClientType(v as ClientType)}
                >
                  <SelectTrigger data-testid="select-client-type">
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    {(Object.keys(CLIENT_TYPE_LABELS) as ClientType[]).map((t) => (
                      <SelectItem key={t} value={t}>
                        {CLIENT_TYPE_LABELS[t]}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </Field>

              <Field
                label={
                  clientType === "company"
                    ? "Полное наименование организации"
                    : "ФИО"
                }
              >
                <Input
                  value={name}
                  onChange={(e) => setName(e.target.value)}
                  placeholder={
                    clientType === "company"
                      ? "ОБЩЕСТВО С ОГРАНИЧЕННОЙ ОТВЕТСТВЕННОСТЬЮ «ПРИМЕР»"
                      : "Иванов Иван Иванович"
                  }
                  data-testid="input-name"
                />
              </Field>

              <div className="grid gap-5 sm:grid-cols-2">
                <Field label="ИНН">
                  <Input
                    value={inn}
                    onChange={(e) => setInn(e.target.value)}
                    placeholder={clientType === "company" ? "7700000000" : "770000000000"}
                    data-testid="input-inn"
                  />
                </Field>
                {clientType !== "individual" && (
                  <Field label={ID_LABEL[clientType]}>
                    <Input
                      value={ogrn}
                      onChange={(e) => setOgrn(e.target.value)}
                      placeholder={clientType === "company" ? "1027700000000" : "300000000000000"}
                      data-testid="input-ogrn"
                    />
                  </Field>
                )}
                {clientType === "company" && (
                  <Field label="КПП">
                    <Input value={kpp} onChange={(e) => setKpp(e.target.value)} placeholder="770001001" data-testid="input-kpp" />
                  </Field>
                )}
              </div>

              <Field
                label="Адрес"
                hint={
                  clientType === "sole_proprietor"
                    ? "В выписке ЕГРИП адрес места жительства скрыт — укажите вручную"
                    : undefined
                }
              >
                <Input
                  value={address}
                  onChange={(e) => setAddress(e.target.value)}
                  placeholder="123456, г. Москва, ул. Примерная, д. 1"
                  data-testid="input-address"
                />
              </Field>

              <div className="grid gap-5 sm:grid-cols-2">
                <Field label="E-mail для переписки">
                  <Input type="email" value={contactEmail} onChange={(e) => setContactEmail(e.target.value)} placeholder="name@example.ru" />
                </Field>
                <Field label="Телефон для переписки">
                  <Input value={contactPhone} onChange={(e) => setContactPhone(e.target.value)} placeholder="+7 900 000-00-00" />
                </Field>
              </div>

              {clientPortal && (
                <label className="flex cursor-pointer items-start gap-3 rounded-xl border border-primary/20 bg-primary/[0.045] p-4">
                  <Checkbox
                    checked={rememberApplicantData}
                    onCheckedChange={(checked) => setRememberApplicantData(checked === true)}
                    data-testid="remember-applicant-data"
                  />
                  <span>
                    <span className="block text-sm font-semibold text-foreground">
                      {user?.applicantProfile
                        ? "Обновить сохранённые данные заявителя"
                        : "Запомнить данные для следующих заявок"}
                    </span>
                    <span className="mt-1 block text-xs leading-relaxed text-muted-foreground">
                      После создания заявки эти реквизиты сохранятся в профиле и автоматически появятся в новой форме. Их всегда можно изменить в разделе «Профиль».
                    </span>
                  </span>
                </label>
              )}

              {clientType === "individual" && (
                <p className="flex items-start gap-2 rounded-lg bg-muted/60 p-3 text-sm text-muted-foreground">
                  <AlertCircle className="w-3 h-3 mt-0.5 shrink-0" />
                  Текст скана распознаётся, но паспортные реквизиты пока нужно
                  проверить и перенести в поля вручную.
                </p>
              )}
            </div>
          )}
      </ProjectStep>

      {/* Шаг 3: обозначение и деятельность */}
      <ProjectStep
        n={3}
        title="Опишите товарный знак"
        description="Укажите обозначение и коротко расскажите, для каких товаров или услуг оно нужно."
      >
          <Field
            label={clientPortal ? <span className="inline-flex items-center gap-1">Вид знака <HelpTip text="Словесный знак защищает название. Изобразительный — картинку. Комбинированный — название и изображение вместе." /></span> : "Вид знака"}
            hint={
              markType === "word"
                ? "Словесный знак — только текст, без изображения."
                : "Для знаков с изображением потребуется файл: приложите его в исходных документах дела."
            }
          >
            <Select
              value={markType}
              onValueChange={(v) => setMarkType(v as MarkType)}
            >
              <SelectTrigger data-testid="select-mark-type">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                {(Object.keys(MARK_TYPE_LABELS) as MarkType[]).map((type) => (
                  <SelectItem key={type} value={type}>
                    {MARK_TYPE_LABELS[type]}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </Field>

          {imageMark && (
            <div className="rounded-2xl border border-primary/25 bg-primary/[0.045] p-5" data-testid="mark-image-field">
              <div className="flex flex-wrap items-start justify-between gap-3">
                <div>
                  <Label className="inline-flex items-center gap-1 text-sm font-semibold">
                    Изображение товарного знака
                    <HelpTip text="Загрузите именно тот логотип или рисунок, который хотите зарегистрировать. Для комбинированного знака защищается изображение вместе с текстом." />
                  </Label>
                  <p className="mt-1 text-xs leading-relaxed text-muted-foreground">
                    PNG или JPEG · до 25 МБ. Изображение попадёт в заявление и будет участвовать в проверке.
                  </p>
                </div>
                <Badge className="bg-amber-100 text-amber-800 hover:bg-amber-100">Обязательно</Badge>
              </div>

              {markImageFile && markImagePreview ? (
                <div className="mt-4 grid gap-4 rounded-xl border border-border bg-background p-4 sm:grid-cols-[140px_1fr]">
                  <div className="flex min-h-32 items-center justify-center rounded-lg bg-white p-2">
                    <img src={markImagePreview} alt="Выбранный товарный знак" className="max-h-28 max-w-full object-contain" />
                  </div>
                  <div className="min-w-0 self-center">
                    <p className="truncate text-sm font-semibold">{markImageFile.name}</p>
                    <p className="mt-1 text-xs text-muted-foreground">{(markImageFile.size / 1024).toFixed(0)} КБ</p>
                    <div className="mt-3 flex flex-wrap gap-2">
                      <label className="inline-flex cursor-pointer items-center gap-2 rounded-full border border-border px-4 py-2 text-xs font-semibold hover:bg-muted">
                        <Upload className="h-4 w-4" /> Заменить
                        <input type="file" accept="image/png,image/jpeg" className="sr-only" onChange={(event) => void chooseMarkImage(event.target.files?.[0] ?? null)} />
                      </label>
                      <button type="button" className="inline-flex items-center gap-2 rounded-full px-4 py-2 text-xs font-semibold text-red-700 hover:bg-red-50" onClick={() => setMarkImageFile(null)}>
                        <Trash2 className="h-4 w-4" /> Удалить
                      </button>
                    </div>
                  </div>
                </div>
              ) : (
                <label className="mt-4 flex min-h-32 cursor-pointer flex-col items-center justify-center rounded-xl border-2 border-dashed border-primary/35 bg-background px-5 text-center hover:border-primary/60">
                  <ImageIcon className="h-7 w-7 text-primary" />
                  <span className="mt-2 text-sm font-semibold">Выбрать изображение</span>
                  <span className="mt-1 text-xs text-muted-foreground">PNG или JPEG</span>
                  <input type="file" accept="image/png,image/jpeg" className="sr-only" data-testid="input-mark-image" onChange={(event) => void chooseMarkImage(event.target.files?.[0] ?? null)} />
                </label>
              )}
              {isInspectingImage && <p className="mt-3 flex items-center gap-2 text-sm font-medium text-[#087c78]"><Loader2 className="h-4 w-4 animate-spin" /> Читаем текст на изображении…</p>}
            </div>
          )}

          <Field
            label={
              markType === "figurative"
                ? "Название обозначения (для дела)"
                : "Заявляемое обозначение"
            }
            hint={
              markType === "figurative"
                ? "У изобразительного знака словесной части нет — укажите рабочее название, чтобы дело было узнаваемо в списке."
                : undefined
            }
          >
            <Input
              value={markName}
              onChange={(e) => setMarkName(e.target.value)}
              placeholder="ЗВЁЗДОЧКА"
              data-testid="input-mark-name"
            />
          </Field>

          {!clientPortal && (
            <Field
              label="Чем занимается заявитель"
              hint="Из этого описания система подберёт классы МКТУ. Для ИП подставляется основной вид деятельности из ЕГРИП."
            >
              <Textarea
                value={businessDescription}
                onChange={(e) => setBusinessDescription(e.target.value)}
                placeholder="Например: производство одежды и продажа через интернет-магазин"
                rows={2}
                data-testid="input-business"
              />
            </Field>
          )}

          <Field label={clientPortal ? <span className="inline-flex items-center gap-1">Что вы продаёте или какие услуги оказываете <HelpTip text="По этому перечню система подберёт классы МКТУ — группы товаров и услуг, для которых будет действовать защита товарного знака." /></span> : "Товары и услуги (если клиент перечислил)"}>
            <Textarea
              value={clientPortal ? clientActivity : goodsServices}
              onChange={(e) => {
                setGoodsServices(e.target.value);
                if (clientPortal) setBusinessDescription(e.target.value);
              }}
              placeholder={clientPortal ? "Например: ремонт квартир, пошив одежды или доставка еды" : "одежда, обувь, головные уборы"}
              rows={2}
              data-testid="input-goods"
            />
          </Field>

          {!clientPortal && <details className="rounded-lg border border-border px-4 py-3 text-sm">
            <summary className="cursor-pointer font-medium text-muted-foreground hover:text-foreground">
              Сведения об обращении (необязательно)
            </summary>
            <div className="space-y-3 mt-3">
              <Field label="От кого (клиент, email, телефон)">
                <Input
                  value={sender}
                  onChange={(e) => setSender(e.target.value)}
                  placeholder="Иванов И. И., ivanov@example.ru"
                  data-testid="input-sender"
                />
              </Field>
              <Field label="Текст обращения">
                <Textarea
                  value={bodyText}
                  onChange={(e) => setBodyText(e.target.value)}
                  placeholder="Что написал клиент. Сохранится в примечаниях дела."
                  rows={2}
                  data-testid="input-body"
                />
              </Field>
            </div>
          </details>}
      </ProjectStep>

      <div className="sticky bottom-0 z-10 flex items-center justify-between border-t border-border bg-background/95 py-5 backdrop-blur">
        <div className="flex items-center gap-3">
          <Button variant="outline" onClick={() => saveDraft(true)} disabled={isSaving}>Сохранить черновик</Button>
          <p className="hidden text-sm text-muted-foreground xl:block">Поля также сохраняются автоматически</p>
        </div>
        <Button size="lg" onClick={() => void submit()} disabled={isSaving} data-testid="button-create-case">
          {isSaving ? (
            <Loader2 className="w-4 h-4 mr-2 animate-spin" />
          ) : (
            <CheckCircle2 className="w-4 h-4 mr-2" />
          )}
          {clientPortal ? "Создать заявку" : "Создать проект"}
        </Button>
      </div>
    </div>
  );
}

function StepBadge({ n }: { n: number }) {
  return (
    <span className="flex h-9 w-9 shrink-0 items-center justify-center rounded-full bg-primary text-sm font-bold text-primary-foreground">
      {n}
    </span>
  );
}

function ProjectStep({
  n,
  title,
  description,
  children,
}: {
  n: number;
  title: string;
  description: string;
  children: React.ReactNode;
}) {
  return (
    <section className="overflow-hidden rounded-2xl border border-[#11113f]/10 bg-white text-[#11113f] shadow-sm">
      <header className="flex items-start gap-4 border-b border-[#11113f]/10 bg-[#edf8f7] px-6 py-5 sm:px-8">
        <StepBadge n={n} />
        <div>
          <h2 className="text-xl font-semibold">{title}</h2>
          <p className="mt-1 text-sm leading-relaxed text-[#626276]">{description}</p>
        </div>
      </header>
      <div className="space-y-5 px-6 py-6 sm:px-8 sm:py-7">{children}</div>
    </section>
  );
}

function Field({
  label,
  hint,
  children,
}: {
  label: React.ReactNode;
  hint?: string;
  children: React.ReactNode;
}) {
  return (
    <div className="space-y-2">
      <Label className="text-sm font-semibold">{label}</Label>
      {children}
      {hint && <p className="text-xs leading-relaxed text-muted-foreground">{hint}</p>}
    </div>
  );
}
