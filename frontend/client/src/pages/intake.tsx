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
  Sparkles,
  Upload,
} from "lucide-react";

const ACCEPTED = ".pdf,.docx,.txt,.png,.jpg,.jpeg";

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
  const [address, setAddress] = useState("");

  // Обозначение и деятельность.
  const [markName, setMarkName] = useState("");
  const [businessDescription, setBusinessDescription] = useState("");
  const [goodsServices, setGoodsServices] = useState("");

  // Обращение (необязательное).
  const [sender, setSender] = useState("");
  const [bodyText, setBodyText] = useState("");

  const [isSaving, setIsSaving] = useState(false);
  const [caseId, setCaseId] = useState<number | null>(null);
  // Ключ идемпотентности на одно заполнение формы: повторный клик
  // не создаст дубль, а следующее дело получит новый ключ.
  const [submissionKey] = useState(() => crypto.randomUUID());

  const clients = Object.values(cases.data?.clientsById ?? {});

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
    setIsReading(true);
    try {
      const result = await api.upload<PrefillResponse>(
        "/intake/prefill-registrant",
        file,
      );

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

  const validate = (): string | null => {
    if (useExistingClient) {
      if (!clientId) return "Выберите клиента или заполните данные нового.";
    } else if (name.trim().length < 2) {
      return "Укажите наименование или ФИО заявителя.";
    }
    if (!markName.trim()) return "Укажите заявляемое обозначение.";
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
              address: address.trim() || null,
            },
        mark_name: markName.trim() || null,
        mark_text: markName.trim() || null,
        business_description: businessDescription.trim() || null,
        goods_services: goodsServices.trim() || null,
      });

      const newCaseId = event.created_case_id ?? event.target_case_id;
      if (!newCaseId) {
        throw new ApiError(500, "Дело не создано");
      }

      // 2. Загружаем приложенные документы в дело и извлекаем реквизиты.
      //    Так документ оказывается в деле, а поля — на вкладке «Сверка».
      let uploaded = 0;
      for (const item of attached) {
        try {
          const doc = await api.upload<{ id: number; processing_status: string }>(
            `/applications/${newCaseId}/source-documents`,
            item.file,
          );
          uploaded += 1;
          // Извлечение имеет смысл только для распознанных выписок.
          if (doc.processing_status === "extracted") {
            await api.post(`/source-documents/${doc.id}/extract`).catch(() => {
              // Для типов без правил извлечения — это норма, не ошибка.
            });
          }
        } catch {
          // Один сбойный файл не должен ронять создание дела.
        }
      }

      setCaseId(newCaseId);
      toast({
        title: `Дело №${newCaseId} создано`,
        description: uploaded
          ? `Документов приложено: ${uploaded}. Реквизиты — на вкладке «Сверка полей».`
          : "Документы не приложены — их можно добавить в карточке дела.",
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
                <p className="text-sm font-medium">Дело №{caseId} создано</p>
                <p className="text-xs text-muted-foreground">
                  Дальше — проверка извлечённых реквизитов на вкладке
                  «Сверка полей» и подтверждение полей.
                </p>
              </div>
            </div>
            <Button size="sm" onClick={() => setLocation(`/applications/${caseId}`)}>
              Открыть дело
              <ArrowRight className="w-3.5 h-3.5 ml-1.5" />
            </Button>
          </CardContent>
        </Card>
      </div>
    );
  }

  return (
    <div className="space-y-4 max-w-3xl" data-testid="intake-page">
      <div className="flex items-center gap-2">
        <Inbox className="w-5 h-5 text-primary" />
        <div>
          <h1 className="text-xl font-bold">Приём обращения</h1>
          <p className="text-sm text-muted-foreground">
            Приложите документы клиента — система заполнит форму, вы проверите
          </p>
        </div>
      </div>

      {/* Шаг 1: документы (первым — с них начинается работа) */}
      <Card>
        <CardHeader className="pb-2">
          <CardTitle className="text-sm font-semibold flex items-center gap-2">
            <StepBadge n={1} />
            Документы клиента
          </CardTitle>
        </CardHeader>
        <CardContent className="space-y-3">
          <p className="text-xs text-muted-foreground">
            Приложите выписку ЕГРЮЛ или ЕГРИП — из неё автоматически
            подставятся наименование, ИНН, ОГРН и адрес. Также можно приложить
            доверенность и изображение обозначения. PDF, DOCX, TXT, PNG, JPG.
          </p>

          <div
            className="rounded-lg border border-dashed border-border p-4 flex flex-col items-center gap-2 text-center"
            data-testid="intake-dropzone"
          >
            <Upload className="w-6 h-6 text-muted-foreground" />
            <Button
              variant="outline"
              size="sm"
              disabled={isReading}
              onClick={() => fileInput.current?.click()}
              data-testid="button-attach"
            >
              {isReading ? (
                <Loader2 className="w-3.5 h-3.5 mr-1.5 animate-spin" />
              ) : (
                <Upload className="w-3.5 h-3.5 mr-1.5" />
              )}
              Приложить документ
            </Button>
            <p className="text-[11px] text-muted-foreground">
              Тип файла проверяется по содержимому, а не по расширению
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
            <div className="space-y-1.5">
              {attached.map((item, index) => (
                <div
                  key={`${item.file.name}-${index}`}
                  className="flex items-start gap-2 rounded-md border border-border px-2.5 py-2"
                >
                  <FileText className="w-4 h-4 shrink-0 mt-0.5 text-muted-foreground" />
                  <div className="min-w-0 flex-1">
                    <p className="text-xs font-medium truncate">{item.file.name}</p>
                    <p className="text-[11px] text-muted-foreground">
                      {DOCUMENT_KIND_LABELS[item.documentKind ?? ""] ??
                        "Тип не определён"}
                    </p>
                    {item.warning && (
                      <p className="text-[11px] text-amber-600 dark:text-amber-500 flex items-start gap-1 mt-0.5">
                        <AlertCircle className="w-3 h-3 mt-0.5 shrink-0" />
                        {item.warning}
                      </p>
                    )}
                  </div>
                  {item.autofilled && (
                    <Badge className="bg-emerald-500/15 text-emerald-700 dark:text-emerald-400 text-[10px] shrink-0">
                      <Sparkles className="w-3 h-3 mr-1" />
                      данные в форме
                    </Badge>
                  )}
                  <button
                    type="button"
                    className="text-[11px] text-muted-foreground hover:text-destructive shrink-0"
                    onClick={() => removeAttachment(index)}
                    data-testid={`remove-attachment-${index}`}
                  >
                    убрать
                  </button>
                </div>
              ))}
            </div>
          )}
        </CardContent>
      </Card>

      {/* Шаг 2: заявитель */}
      <Card>
        <CardHeader className="pb-2">
          <CardTitle className="text-sm font-semibold flex items-center gap-2">
            <StepBadge n={2} />
            Заявитель
          </CardTitle>
        </CardHeader>
        <CardContent className="space-y-3">
          <div className="flex gap-2">
            <Button
              type="button"
              size="sm"
              variant={!useExistingClient ? "default" : "outline"}
              onClick={() => setUseExistingClient(false)}
            >
              Новый клиент
            </Button>
            <Button
              type="button"
              size="sm"
              variant={useExistingClient ? "default" : "outline"}
              onClick={() => setUseExistingClient(true)}
            >
              Существующий
            </Button>
          </div>

          {useExistingClient ? (
            <Field label="Клиент">
              <Select value={clientId} onValueChange={setClientId}>
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
            <>
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

              <div className="grid gap-3 sm:grid-cols-2">
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

              {clientType === "individual" && (
                <p className="text-[11px] text-muted-foreground flex items-start gap-1">
                  <AlertCircle className="w-3 h-3 mt-0.5 shrink-0" />
                  Паспортные данные физлица вносятся вручную: автоизвлечение из
                  скана паспорта пока не поддерживается.
                </p>
              )}
            </>
          )}
        </CardContent>
      </Card>

      {/* Шаг 3: обозначение и деятельность */}
      <Card>
        <CardHeader className="pb-2">
          <CardTitle className="text-sm font-semibold flex items-center gap-2">
            <StepBadge n={3} />
            Обозначение и деятельность
          </CardTitle>
        </CardHeader>
        <CardContent className="space-y-3">
          <Field label="Заявляемое обозначение">
            <Input
              value={markName}
              onChange={(e) => setMarkName(e.target.value)}
              placeholder="ЗВЁЗДОЧКА"
              data-testid="input-mark-name"
            />
          </Field>

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

          <Field label="Товары и услуги (если клиент перечислил)">
            <Textarea
              value={goodsServices}
              onChange={(e) => setGoodsServices(e.target.value)}
              placeholder="одежда, обувь, головные уборы"
              rows={2}
              data-testid="input-goods"
            />
          </Field>

          <Separator />

          <details className="text-xs">
            <summary className="cursor-pointer text-muted-foreground">
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
          </details>
        </CardContent>
      </Card>

      <div className="flex justify-end">
        <Button onClick={() => void submit()} disabled={isSaving} data-testid="button-create-case">
          {isSaving ? (
            <Loader2 className="w-4 h-4 mr-2 animate-spin" />
          ) : (
            <CheckCircle2 className="w-4 h-4 mr-2" />
          )}
          Создать дело
        </Button>
      </div>
    </div>
  );
}

function StepBadge({ n }: { n: number }) {
  return (
    <span className="flex h-5 w-5 items-center justify-center rounded-full bg-primary text-primary-foreground text-[10px] font-bold">
      {n}
    </span>
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
