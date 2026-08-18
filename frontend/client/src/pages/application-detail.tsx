import { useState } from "react";
import { useCase } from "@/lib/use-cases";
import { useApi } from "@/lib/use-api";
import type { Application, Client } from "@shared/schema";
import { useRoute } from "wouter";
import { useAuth } from "@/lib/auth";
import {
  STATUS_LABELS, STATUS_COLORS, MARK_TYPE_LABELS, CLIENT_TYPE_LABELS,
} from "@shared/schema";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import { useToast } from "@/hooks/use-toast";
import { api, ApiError } from "@/lib/api";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { SourceDocumentsTab } from "@/components/source-documents-tab";
import { FieldConfirmationTab } from "@/components/field-confirmation-tab";
import {
  DocumentPackagesTab,
} from "@/components/case-tabs";
// Классы МКТУ, абсолютные основания и конфликты — части одной проверки,
// поэтому живут в общей вкладке, а не в трёх разных.
import { LegalAnalysisTab } from "@/components/legal-analysis-tab";
import { ApplicationDraftTab } from "@/components/application-draft-tab";
import { ProfessionalFeeEstimate } from "@/components/professional-fee-estimate";
import { OfficeActionResponse } from "@/components/office-action-response";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { Progress } from "@/components/ui/progress";
import { Separator } from "@/components/ui/separator";
import {
  Collapsible, CollapsibleContent, CollapsibleTrigger,
} from "@/components/ui/collapsible";
import {
  Select, SelectContent, SelectItem, SelectTrigger, SelectValue,
} from "@/components/ui/select";
import {
  Info, Shield, Layers, Crosshair, FileCheck, FileText,
  History, CheckCircle2, XCircle, AlertTriangle, ChevronDown,
  Send, Download, Eye, Clock, ArrowRight, Gavel, Upload, ClipboardList, Loader2, AlertCircle,
  Check, X, Minus, ClipboardCheck, FileSignature,
  MessageSquareText,
} from "lucide-react";
import { cn } from "@/lib/utils";

// ========== TAB: GENERAL INFO ==========
/**
 * Общие сведения дела.
 *
 * Данные правятся прямо здесь: часть сведений приходит со слов
 * клиента и уточняется по ходу работы, а отправлять специалиста
 * за этим в другой раздел незачем.
 */
function GeneralInfoTab({
  app,
  client,
  onSaved,
}: {
  app: Application;
  client: Client | null;
  onSaved: () => void;
}) {

  return (
    <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
      <Card className="border border-card-border">
        <CardHeader className="pb-2">
          <CardTitle className="text-sm font-semibold flex items-center gap-2">
            <Info className="w-4 h-4 text-primary" /> Информация о заявке
          </CardTitle>
        </CardHeader>
        <CardContent className="space-y-3">
          <InfoRow label="Номер" value={`#${app.id}`} mono />
          <InfoRow label="Статус">
            <Badge className={cn("text-[10px]", STATUS_COLORS[app.status])}>{STATUS_LABELS[app.status]}</Badge>
          </InfoRow>
          <AssigneeRow appId={app.id} value={app.assigneeId} onSaved={onSaved} />
          <InfoRow label="Территория" value={app.territory || "—"} />
          <InfoRow label="Приоритет" value={app.priorityClaim || "Нет"} />
          <InfoRow label="Создана" value={new Date(app.createdAt).toLocaleDateString("ru-RU")} />
          <InfoRow label="Обновлена" value={new Date(app.updatedAt).toLocaleDateString("ru-RU")} />
          {app.notes && <InfoRow label="Примечания" value={app.notes} />}
        </CardContent>
      </Card>

      <Card className="border border-card-border">
        <CardHeader className="pb-2">
          <CardTitle className="text-sm font-semibold">Обозначение</CardTitle>
        </CardHeader>
        <CardContent className="space-y-3">
          <EditableRow
            appId={app.id}
            label="Наименование"
            field="mark_name"
            value={app.markName}
            onSaved={onSaved}
          />
          <EditableSelectRow
            appId={app.id}
            label="Вид знака"
            field="mark_type"
            value={app.markType}
            options={MARK_TYPE_LABELS}
            onSaved={onSaved}
          />
          <EditableRow
            appId={app.id}
            label="Текст"
            field="mark_text"
            value={app.markText}
            onSaved={onSaved}
          />
          {app.colorsClaimed && <InfoRow label="Цвета" value={app.colorsClaimed} />}
          {app.transliteration && <InfoRow label="Транслитерация" value={app.transliteration} mono />}
          {app.translation && <InfoRow label="Перевод" value={app.translation} />}
          <EditableRow
            appId={app.id}
            label="Описание"
            field="description_of_mark"
            value={app.descriptionOfMark}
            multiline
            onSaved={onSaved}
          />
        </CardContent>
      </Card>

      {client && (
        <Card className="border border-card-border">
          <CardHeader className="pb-2">
            <CardTitle className="text-sm font-semibold">Клиент</CardTitle>
          </CardHeader>
          <CardContent className="space-y-3">
            <EditableRow
              clientId={client.id}
              label="Наименование"
              field="full_name_or_company_name"
              value={client.fullNameOrCompanyName}
              onSaved={onSaved}
            />
            <InfoRow label="Тип" value={CLIENT_TYPE_LABELS[client.type]} />
            <EditableRow
              clientId={client.id}
              label="Контакт"
              field="contact_person"
              value={client.contactPerson}
              onSaved={onSaved}
            />
            <EditableRow
              clientId={client.id}
              label="Email"
              field="email"
              value={client.email}
              onSaved={onSaved}
            />
            <EditableRow
              clientId={client.id}
              label="Телефон"
              field="phone"
              value={client.phone}
              onSaved={onSaved}
            />
            <EditableRow
              clientId={client.id}
              label="ИНН"
              field="inn"
              value={client.inn}
              onSaved={onSaved}
            />
            <EditableRow
              clientId={client.id}
              label="ОГРН / ОГРНИП"
              field="ogrn_or_ogrnip"
              value={client.ogrnOrOgrnip}
              onSaved={onSaved}
            />
            <EditableRow
              clientId={client.id}
              label="Адрес"
              field="address"
              value={client.address}
              multiline
              onSaved={onSaved}
            />
          </CardContent>
        </Card>
      )}

      <Card className="border border-card-border">
        <CardHeader className="pb-2">
          <CardTitle className="text-sm font-semibold">Товары и услуги</CardTitle>
        </CardHeader>
        <CardContent className="space-y-3">
          <EditableRow
            appId={app.id}
            label="Чем занимается"
            field="business_description"
            value={app.businessDescription}
            multiline
            onSaved={onSaved}
          />
          <Separator />
          <EditableRow
            appId={app.id}
            label="Товары и услуги"
            field="goods_services_raw"
            value={app.goodsServicesRaw}
            multiline
            onSaved={onSaved}
          />
        </CardContent>
      </Card>
    </div>
  );
}








/**
 * Строка сведений, редактируемая по месту.
 *
 * Сохраняет одно поле дела: точечная правка не должна затрагивать
 * остальные значения, которые специалист не трогал.
 */
function EditableRow({
  appId,
  clientId,
  label,
  field,
  value,
  multiline,
  onSaved,
}: {
  appId?: number;
  /** Если задан — правится карточка клиента, а не дела. */
  clientId?: number;
  label: string;
  field: string;
  value?: string | null;
  multiline?: boolean;
  onSaved: () => void;
}) {
  const { toast } = useToast();
  const [isEditing, setIsEditing] = useState(false);
  const [draft, setDraft] = useState(value ?? "");
  const [isSaving, setIsSaving] = useState(false);

  const save = async () => {
    setIsSaving(true);
    try {
      const path =
        clientId != null ? `/clients/${clientId}` : `/applications/${appId}`;
      await api.put(path, { [field]: draft.trim() });
      toast({ title: `Сохранено: ${label}` });
      setIsEditing(false);
      onSaved();
    } catch (e) {
      toast({
        title: "Не удалось сохранить",
        description: e instanceof ApiError ? e.message : "Неизвестная ошибка",
        variant: "destructive",
      });
    } finally {
      setIsSaving(false);
    }
  };

  if (isEditing) {
    return (
      <div className="flex flex-col sm:flex-row sm:items-start gap-1 sm:gap-4">
        <span className="text-xs font-medium text-muted-foreground sm:w-32 shrink-0 pt-1.5">
          {label}
        </span>
        <div className="flex-1 flex items-start gap-2">
          {multiline ? (
            <Textarea
              autoFocus
              value={draft}
              onChange={(e) => setDraft(e.target.value)}
              rows={2}
              className="text-sm"
            />
          ) : (
            <Input
              autoFocus
              value={draft}
              onChange={(e) => setDraft(e.target.value)}
              className="h-8 text-sm"
            />
          )}
          <Button size="sm" className="h-8" disabled={isSaving} onClick={() => void save()}>
            {isSaving ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : "ОК"}
          </Button>
          <Button
            size="sm"
            variant="ghost"
            className="h-8"
            onClick={() => {
              setIsEditing(false);
              setDraft(value ?? "");
            }}
          >
            Отмена
          </Button>
        </div>
      </div>
    );
  }

  return (
    <div className="flex flex-col sm:flex-row sm:items-start gap-1 sm:gap-4">
      <span className="text-xs font-medium text-muted-foreground sm:w-32 shrink-0">
        {label}
      </span>
      <span className="text-sm flex-1">{value || "—"}</span>
      <Button
        size="sm"
        variant="ghost"
        className="h-6 px-2 text-[11px] text-muted-foreground shrink-0"
        onClick={() => setIsEditing(true)}
        data-testid={`edit-${field}`}
      >
        Изменить
      </Button>
    </div>
  );
}

/**
 * Выбор значения из списка прямо в карточке.
 *
 * Вид знака определяет и состав заявления, и то, нужен ли файл
 * с изображением, — поэтому меняется здесь, а не в отдельной форме.
 */
function EditableSelectRow({
  appId,
  label,
  field,
  value,
  options,
  onSaved,
}: {
  appId: number;
  label: string;
  field: string;
  value: string;
  options: Record<string, string>;
  onSaved: () => void;
}) {
  const { toast } = useToast();
  const [isSaving, setIsSaving] = useState(false);

  const change = async (next: string) => {
    setIsSaving(true);
    try {
      await api.put(`/applications/${appId}`, { [field]: next });
      toast({ title: `Сохранено: ${label}` });
      onSaved();
    } catch (e) {
      toast({
        title: "Не удалось сохранить",
        description: e instanceof ApiError ? e.message : "Неизвестная ошибка",
        variant: "destructive",
      });
    } finally {
      setIsSaving(false);
    }
  };

  return (
    <div className="flex flex-col sm:flex-row sm:items-center gap-1 sm:gap-4">
      <span className="text-xs font-medium text-muted-foreground sm:w-32 shrink-0">
        {label}
      </span>
      <Select value={value} onValueChange={(v) => void change(v)} disabled={isSaving}>
        <SelectTrigger className="h-8 w-56 text-sm" data-testid={`select-${field}`}>
          <SelectValue />
        </SelectTrigger>
        <SelectContent>
          {Object.entries(options).map(([key, title]) => (
            <SelectItem key={key} value={key} className="text-sm">
              {title}
            </SelectItem>
          ))}
        </SelectContent>
      </Select>
    </div>
  );
}

/**
 * Исполнитель по делу.
 *
 * Назначение определяет и видимость: специалист видит дела, которые
 * ведёт. Поэтому список ограничен теми, кто вообще работает с делами.
 */
function AssigneeRow({
  appId,
  value,
  onSaved,
}: {
  appId: number;
  value?: number | null;
  onSaved: () => void;
}) {
  const { toast } = useToast();
  const users = useApi<{ items: { id: number; full_name: string | null; email: string; role: string; is_active: boolean }[] }>(
    "/users?page=1&page_size=100",
  );
  const [isSaving, setIsSaving] = useState(false);

  // Клиенту дела не назначают, отключённым — тоже.
  const candidates = (users.data?.items ?? []).filter(
    (u) => u.is_active && u.role !== "client",
  );

  const assign = async (next: string) => {
    setIsSaving(true);
    try {
      await api.put(`/applications/${appId}`, {
        assigned_lawyer_id: next === "none" ? null : Number(next),
      });
      toast({ title: "Исполнитель назначен" });
      onSaved();
    } catch (e) {
      toast({
        title: "Не удалось назначить исполнителя",
        description: e instanceof ApiError ? e.message : "Неизвестная ошибка",
        variant: "destructive",
      });
    } finally {
      setIsSaving(false);
    }
  };

  return (
    <div className="flex flex-col sm:flex-row sm:items-center gap-1 sm:gap-4">
      <span className="text-xs font-medium text-muted-foreground sm:w-32 shrink-0">
        Исполнитель
      </span>
      <Select
        value={value ? String(value) : "none"}
        onValueChange={(v) => void assign(v)}
        disabled={isSaving || users.isLoading}
      >
        <SelectTrigger className="h-8 w-64 text-sm" data-testid="select-assignee">
          <SelectValue placeholder="Не назначен" />
        </SelectTrigger>
        <SelectContent>
          <SelectItem value="none" className="text-sm">
            Не назначен
          </SelectItem>
          {candidates.map((user) => (
            <SelectItem key={user.id} value={String(user.id)} className="text-sm">
              {user.full_name || user.email}
            </SelectItem>
          ))}
        </SelectContent>
      </Select>
    </div>
  );
}

// ========== INFO ROW HELPER ==========
function InfoRow({ label, value, mono, children }: { label: string; value?: string; mono?: boolean; children?: React.ReactNode }) {
  return (
    <div className="flex flex-col sm:flex-row sm:items-start gap-1 sm:gap-4">
      <span className="text-xs font-medium text-muted-foreground sm:w-32 shrink-0">{label}</span>
      {children || <span className={cn("text-sm", mono && "font-mono")}>{value || "—"}</span>}
    </div>
  );
}

// ========== MAIN PAGE ==========
export default function ApplicationDetailPage() {
  const [, params] = useRoute("/applications/:id");
  const { user } = useAuth();
  const appId = params?.id ? parseInt(params.id) : 0;
  // Меняется после извлечения реквизитов, чтобы вкладка сверки
  // перечитала данные при следующем открытии.
  const [fieldsRefreshKey, setFieldsRefreshKey] = useState(0);

  // Шапка карточки берётся из API: раньше она читалась из моков и
  // расходилась с реальными данными во вкладках.
  const { data, isLoading, error, reload } = useCase(appId);

  if (isLoading) {
    return (
      <div className="flex items-center justify-center gap-2 min-h-[50vh] text-muted-foreground">
        <Loader2 className="w-4 h-4 animate-spin" />
        <span className="text-sm">Загрузка дела…</span>
      </div>
    );
  }

  if (error || !data) {
    return (
      <div className="flex items-start gap-2 rounded-md border border-destructive/40 bg-destructive/10 px-3 py-2">
        <AlertCircle className="w-4 h-4 shrink-0 mt-0.5 text-destructive" />
        <p className="flex-1 text-sm" data-testid="application-error">
          {error ?? "Дело не найдено"}
        </p>
        <Button variant="ghost" size="sm" onClick={reload}>
          Повторить
        </Button>
      </div>
    );
  }

  const app = data.application;
  const client = data.client;

  return (
    <div className="space-y-4" data-testid="application-detail-page">
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-2">
        <div>
          <div className="flex items-center gap-3">
            <h1 className="text-3xl font-semibold">{app.markName}</h1>
            <Badge className={cn("text-[10px]", STATUS_COLORS[app.status])}>
              {STATUS_LABELS[app.status]}
            </Badge>
          </div>
          <p className="text-sm text-muted-foreground mt-0.5">
            Заявка #{app.id} · {MARK_TYPE_LABELS[app.markType]}
            {client ? ` · ${client.shortName}` : ""}
          </p>
        </div>
      </div>

      <Tabs defaultValue="overview" className="w-full">
        <TabsList className="grid h-auto w-full grid-cols-2 overflow-hidden rounded-lg border border-border bg-card p-0 md:grid-cols-4 xl:grid-cols-7">
          {[
            { value: "overview", label: "Карточка", hint: "сведения", icon: Info },
            { value: "data", label: "Данные", hint: "документы и сверка", icon: ClipboardCheck },
            { value: "review", label: "Экспертиза", hint: "классы и риски", icon: Shield },
            { value: "application", label: "Заявка", hint: "черновик заявления", icon: FileSignature },
            { value: "fees", label: "Пошлины", hint: "расчёт к оплате", icon: FileCheck },
            { value: "documents", label: "Документы", hint: "готовые файлы", icon: Download },
            { value: "response", label: "Ответ", hint: "переписка с Роспатентом", icon: MessageSquareText },
          ].map(tab => (
            <TabsTrigger
              key={tab.value}
              value={tab.value}
              className="relative flex min-w-0 items-center justify-start gap-3 rounded-none border-r border-border px-3 py-4 text-left last:border-r-0 data-[state=active]:bg-primary/[0.07] data-[state=active]:text-foreground data-[state=active]:shadow-none sm:px-5"
              data-testid={`tab-${tab.value}`}
            >
              <span className="flex h-7 w-7 shrink-0 items-center justify-center rounded-full border border-current text-xs data-[state=active]:border-primary">
                <tab.icon className="h-3.5 w-3.5" />
              </span>
              <span className="min-w-0">
                <span className="block truncate text-sm font-semibold sm:text-base">{tab.label}</span>
                <span className="hidden truncate text-xs font-normal text-muted-foreground md:block">{tab.hint}</span>
              </span>
            </TabsTrigger>
          ))}
        </TabsList>

        <div className="mt-6">
          <TabsContent value="overview">
            <GeneralInfoTab app={app} client={client} onSaved={reload} />
          </TabsContent>
          <TabsContent value="data" className="space-y-8">
            <section>
              <div className="mb-4 flex items-start gap-3">
                <span className="flex h-7 w-7 shrink-0 items-center justify-center rounded-full bg-primary text-xs font-semibold text-white">1</span>
                <div>
                  <h2 className="text-base font-semibold">Загрузите исходные документы</h2>
                  <p className="text-sm text-muted-foreground">Система извлечёт реквизиты, но не подтвердит их за специалиста.</p>
                </div>
              </div>
              <SourceDocumentsTab appId={appId} onExtracted={() => setFieldsRefreshKey(k => k + 1)} />
            </section>
            <section className="border-t border-border pt-7">
              <div className="mb-4 flex items-start gap-3">
                <span className="flex h-7 w-7 shrink-0 items-center justify-center rounded-full bg-primary text-xs font-semibold text-white">2</span>
                <div>
                  <h2 className="text-base font-semibold">Проверьте извлечённые данные</h2>
                  <p className="text-sm text-muted-foreground">Подтвердите спорные значения до формирования заявления.</p>
                </div>
              </div>
              <FieldConfirmationTab key={fieldsRefreshKey} appId={appId} />
            </section>
          </TabsContent>
          <TabsContent value="review"><LegalAnalysisTab appId={appId} /></TabsContent>
          <TabsContent value="application" className="space-y-8">
            <section>
              <h2 className="mb-3 text-xl font-semibold">Заявление</h2>
              <ApplicationDraftTab appId={appId} />
            </section>
          </TabsContent>
          <TabsContent value="fees">
            {(user?.role === "admin" || user?.role === "lawyer") && (
              <section>
                <h2 className="mb-3 text-xl font-semibold">Пошлины</h2>
                <ProfessionalFeeEstimate appId={appId} />
              </section>
            )}
          </TabsContent>
          <TabsContent value="documents">
            <section>
              <h2 className="mb-3 text-xl font-semibold">Готовые документы</h2>
              <DocumentPackagesTab appId={appId} />
            </section>
          </TabsContent>
          <TabsContent value="response">
            <OfficeActionResponse appId={appId} audience="professional" />
          </TabsContent>
        </div>
      </Tabs>
    </div>
  );
}
