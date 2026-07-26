/**
 * Приём обращения от клиента.
 *
 * Пока нет интеграции с CRM и почтой, юрист вносит сюда то, что
 * прислал клиент: текст обращения, данные о компании и обозначении,
 * а также сами документы. Обращение регистрируется как событие канала
 * manual_upload и проходит тот же путь, что будущие CRM и webhook.
 */

import { useRef, useState } from "react";
import { useLocation } from "wouter";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
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
import { cn } from "@/lib/utils";
import {
  AlertCircle,
  ArrowRight,
  CheckCircle2,
  FileText,
  Inbox,
  Loader2,
  Paperclip,
  Trash2,
  Upload,
} from "lucide-react";

const ACCEPTED = ".pdf,.docx,.txt,.png,.jpg,.jpeg";

interface AttachmentResult {
  accepted: boolean;
  document_id?: number;
  original_filename: string;
  document_kind?: string;
  processing_status?: string;
  page_count?: number | null;
  error_message?: string | null;
}

export default function IntakePage() {
  const { toast } = useToast();
  const [, setLocation] = useLocation();
  const fileInput = useRef<HTMLInputElement>(null);
  const cases = useCases();

  // Шаг 1 — сведения об обращении.
  const [sender, setSender] = useState("");
  const [subject, setSubject] = useState("");
  const [bodyText, setBodyText] = useState("");

  // Шаг 1 — данные дела.
  const [useExistingClient, setUseExistingClient] = useState(true);
  const [clientId, setClientId] = useState<string>("");
  const [newClientName, setNewClientName] = useState("");
  const [newClientInn, setNewClientInn] = useState("");
  const [markName, setMarkName] = useState("");
  const [businessDescription, setBusinessDescription] = useState("");
  const [goodsServices, setGoodsServices] = useState("");

  // Результат регистрации.
  const [eventId, setEventId] = useState<number | null>(null);
  const [caseId, setCaseId] = useState<number | null>(null);
  const [attachments, setAttachments] = useState<AttachmentResult[]>([]);
  const [isSaving, setIsSaving] = useState(false);
  const [isUploading, setIsUploading] = useState(false);

  const clients = Object.values(cases.data?.clientsById ?? {});

  const register = async () => {
    if (!useExistingClient && newClientName.trim().length < 2) {
      toast({
        title: "Укажите клиента",
        description: "Заполните наименование или выберите существующего клиента.",
        variant: "destructive",
      });
      return;
    }
    if (useExistingClient && !clientId) {
      toast({
        title: "Выберите клиента",
        description: "Либо создайте нового по данным, присланным клиентом.",
        variant: "destructive",
      });
      return;
    }

    setIsSaving(true);
    try {
      const result = await api.post<{
        id: number;
        created_case_id: number | null;
        target_case_id: number | null;
        is_duplicate: boolean;
        notice?: string;
      }>("/inbound/events", {
        sender: sender || null,
        subject: subject || null,
        body_text: bodyText || null,
        create_case: true,
        client_id: useExistingClient ? Number(clientId) : null,
        new_client: useExistingClient
          ? null
          : {
              type: "company",
              full_name_or_company_name: newClientName,
              inn: newClientInn || null,
            },
        mark_name: markName || null,
        mark_text: markName || null,
        business_description: businessDescription || null,
        goods_services: goodsServices || null,
      });

      setEventId(result.id);
      setCaseId(result.created_case_id ?? result.target_case_id);

      if (result.is_duplicate) {
        toast({
          title: "Обращение уже принято",
          description:
            result.notice ??
            "Событие с таким содержимым зарегистрировано ранее. Дубликат не создан.",
        });
      } else {
        toast({
          title: "Обращение принято",
          description: result.created_case_id
            ? `Создано дело №${result.created_case_id}. Приложите документы клиента.`
            : "Теперь можно приложить документы.",
        });
      }
    } catch (e) {
      toast({
        title: "Не удалось принять обращение",
        description: e instanceof ApiError ? e.message : "Неизвестная ошибка",
        variant: "destructive",
      });
    } finally {
      setIsSaving(false);
    }
  };

  const upload = async (file: File) => {
    if (!eventId) return;
    setIsUploading(true);
    try {
      const result = await api.upload<AttachmentResult>(
        `/inbound/events/${eventId}/attachments`,
        file,
      );
      setAttachments((prev) => [...prev, result]);
      toast({
        title: result.accepted ? "Документ приложен" : "Файл отклонён",
        description: result.accepted
          ? `${result.original_filename}${
              result.page_count ? ` — страниц: ${result.page_count}` : ""
            }`
          : result.error_message ?? undefined,
        variant: result.accepted ? undefined : "destructive",
      });
    } catch (e) {
      toast({
        title: "Не удалось загрузить файл",
        description: e instanceof ApiError ? e.message : "Неизвестная ошибка",
        variant: "destructive",
      });
    } finally {
      setIsUploading(false);
      if (fileInput.current) fileInput.current.value = "";
    }
  };

  return (
    <div className="space-y-4 max-w-3xl" data-testid="intake-page">
      <div className="flex items-center gap-2">
        <Inbox className="w-5 h-5 text-primary" />
        <div>
          <h1 className="text-xl font-bold">Приём обращения</h1>
          <p className="text-sm text-muted-foreground">
            Внесите данные и документы, присланные клиентом
          </p>
        </div>
      </div>

      {/* Шаг 1: сведения об обращении */}
      <Card>
        <CardHeader className="pb-2">
          <CardTitle className="text-sm font-semibold flex items-center gap-2">
            <span
              className={cn(
                "flex h-5 w-5 items-center justify-center rounded-full text-[10px] font-bold",
                eventId ? "bg-emerald-500 text-white" : "bg-primary text-primary-foreground",
              )}
            >
              {eventId ? "✓" : "1"}
            </span>
            Обращение и данные дела
          </CardTitle>
        </CardHeader>
        <CardContent className="space-y-3">
          <div className="grid gap-3 sm:grid-cols-2">
            <Field label="От кого (клиент, email, телефон)">
              <Input
                value={sender}
                onChange={(e) => setSender(e.target.value)}
                placeholder="Иванов И. И., ivanov@example.ru"
                disabled={!!eventId}
                data-testid="input-sender"
              />
            </Field>
            <Field label="Тема обращения">
              <Input
                value={subject}
                onChange={(e) => setSubject(e.target.value)}
                placeholder="Регистрация товарного знака"
                disabled={!!eventId}
                data-testid="input-subject"
              />
            </Field>
          </div>

          <Field label="Текст обращения">
            <Textarea
              value={bodyText}
              onChange={(e) => setBodyText(e.target.value)}
              placeholder="Что написал клиент. Текст сохранится в примечаниях дела."
              rows={3}
              disabled={!!eventId}
              data-testid="input-body"
            />
          </Field>

          <Separator />

          <div className="flex gap-2">
            <Button
              type="button"
              size="sm"
              variant={useExistingClient ? "default" : "outline"}
              onClick={() => setUseExistingClient(true)}
              disabled={!!eventId}
            >
              Существующий клиент
            </Button>
            <Button
              type="button"
              size="sm"
              variant={!useExistingClient ? "default" : "outline"}
              onClick={() => setUseExistingClient(false)}
              disabled={!!eventId}
            >
              Новый клиент
            </Button>
          </div>

          {useExistingClient ? (
            <Field label="Клиент">
              <Select
                value={clientId}
                onValueChange={setClientId}
                disabled={!!eventId}
              >
                <SelectTrigger data-testid="select-client">
                  <SelectValue placeholder="Выберите клиента" />
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
          ) : (
            <div className="grid gap-3 sm:grid-cols-2">
              <Field label="Наименование организации или ФИО">
                <Input
                  value={newClientName}
                  onChange={(e) => setNewClientName(e.target.value)}
                  placeholder='ООО «Пример»'
                  disabled={!!eventId}
                  data-testid="input-new-client-name"
                />
              </Field>
              <Field label="ИНН (со слов клиента)">
                <Input
                  value={newClientInn}
                  onChange={(e) => setNewClientInn(e.target.value)}
                  placeholder="7700000000"
                  disabled={!!eventId}
                  data-testid="input-new-client-inn"
                />
              </Field>
            </div>
          )}

          <Field label="Заявляемое обозначение">
            <Input
              value={markName}
              onChange={(e) => setMarkName(e.target.value)}
              placeholder="ЗВЁЗДОЧКА"
              disabled={!!eventId}
              data-testid="input-mark-name"
            />
          </Field>

          <Field
            label="Чем занимается компания"
            hint="Из этого описания система подберёт классы МКТУ"
          >
            <Textarea
              value={businessDescription}
              onChange={(e) => setBusinessDescription(e.target.value)}
              placeholder="Например: занимаемся производством одежды и продаём её через интернет-магазин"
              rows={2}
              disabled={!!eventId}
              data-testid="input-business"
            />
          </Field>

          <Field label="Товары и услуги (если клиент перечислил)">
            <Textarea
              value={goodsServices}
              onChange={(e) => setGoodsServices(e.target.value)}
              placeholder="одежда, обувь, головные уборы"
              rows={2}
              disabled={!!eventId}
              data-testid="input-goods"
            />
          </Field>

          {!eventId && (
            <Button
              onClick={() => void register()}
              disabled={isSaving}
              data-testid="button-register-intake"
            >
              {isSaving ? (
                <Loader2 className="w-4 h-4 mr-2 animate-spin" />
              ) : (
                <CheckCircle2 className="w-4 h-4 mr-2" />
              )}
              Принять обращение
            </Button>
          )}
        </CardContent>
      </Card>

      {/* Шаг 2: документы */}
      <Card className={cn(!eventId && "opacity-60")}>
        <CardHeader className="pb-2">
          <CardTitle className="text-sm font-semibold flex items-center gap-2">
            <span className="flex h-5 w-5 items-center justify-center rounded-full bg-muted text-[10px] font-bold">
              2
            </span>
            Документы от клиента
          </CardTitle>
        </CardHeader>
        <CardContent className="space-y-3">
          <p className="text-xs text-muted-foreground">
            Выписка ЕГРЮЛ, заполненный бланк заявки, доверенность, изображение
            обозначения. PDF, DOCX, TXT, PNG, JPG. Тип файла проверяется
            по содержимому.
          </p>

          <Button
            variant="outline"
            size="sm"
            disabled={!eventId || isUploading}
            onClick={() => fileInput.current?.click()}
            data-testid="button-attach"
          >
            {isUploading ? (
              <Loader2 className="w-3.5 h-3.5 mr-1.5 animate-spin" />
            ) : (
              <Upload className="w-3.5 h-3.5 mr-1.5" />
            )}
            Приложить документ
          </Button>
          <input
            ref={fileInput}
            type="file"
            accept={ACCEPTED}
            className="hidden"
            data-testid="input-attachment"
            onChange={(e) => {
              const file = e.target.files?.[0];
              if (file) void upload(file);
            }}
          />

          {attachments.length > 0 && (
            <div className="space-y-1.5">
              {attachments.map((attachment, index) => (
                <div
                  key={`${attachment.original_filename}-${index}`}
                  className={cn(
                    "flex items-start gap-2 rounded-md border px-2.5 py-2",
                    attachment.accepted
                      ? "border-border"
                      : "border-destructive/40 bg-destructive/5",
                  )}
                >
                  {attachment.accepted ? (
                    <FileText className="w-4 h-4 shrink-0 mt-0.5 text-muted-foreground" />
                  ) : (
                    <AlertCircle className="w-4 h-4 shrink-0 mt-0.5 text-destructive" />
                  )}
                  <div className="min-w-0 flex-1">
                    <p className="text-xs font-medium truncate">
                      {attachment.original_filename}
                    </p>
                    {attachment.accepted ? (
                      <p className="text-[11px] text-muted-foreground">
                        {DOCUMENT_KIND_LABELS[attachment.document_kind ?? ""] ??
                          attachment.document_kind}
                        {attachment.page_count
                          ? ` · страниц: ${attachment.page_count}`
                          : ""}
                      </p>
                    ) : (
                      <p className="text-[11px] text-destructive">
                        {attachment.error_message}
                      </p>
                    )}
                  </div>
                  {attachment.accepted && (
                    <Badge variant="secondary" className="text-[10px]">
                      принят
                    </Badge>
                  )}
                </div>
              ))}
            </div>
          )}
        </CardContent>
      </Card>

      {/* Шаг 3: переход в дело */}
      {caseId && (
        <Card className="border-primary/40">
          <CardContent className="p-3 flex items-center justify-between gap-3">
            <div>
              <p className="text-sm font-medium">Дело №{caseId} создано</p>
              <p className="text-xs text-muted-foreground">
                Дальше: извлечение реквизитов из выписки и подтверждение полей.
              </p>
            </div>
            <Button
              size="sm"
              onClick={() => setLocation(`/applications/${caseId}`)}
              data-testid="button-open-case"
            >
              Открыть дело
              <ArrowRight className="w-3.5 h-3.5 ml-1.5" />
            </Button>
          </CardContent>
        </Card>
      )}
    </div>
  );
}

function Field({
  label,
  hint,
  children,
}: {
  label: string;
  hint?: string;
  children: React.ReactNode;
}) {
  return (
    <div className="space-y-1">
      <Label className="text-xs font-medium">{label}</Label>
      {children}
      {hint && <p className="text-[10px] text-muted-foreground">{hint}</p>}
    </div>
  );
}
