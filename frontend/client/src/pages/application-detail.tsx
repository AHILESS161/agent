import { useState } from "react";
import { useCase } from "@/lib/use-cases";
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
  RecommendationsTab,
  DocumentPackagesTab,
  StatusHistoryTab,
} from "@/components/case-tabs";
// Классы МКТУ, абсолютные основания и конфликты — части одной проверки,
// поэтому живут в общей вкладке, а не в трёх разных.
import { LegalAnalysisTab } from "@/components/legal-analysis-tab";
import { ApplicationDraftTab } from "@/components/application-draft-tab";
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
          <InfoRow
            label="Исполнитель"
            value={app.assigneeId ? `Пользователь #${app.assigneeId}` : "Не назначен"}
          />
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
          <InfoRow label="Вид" value={MARK_TYPE_LABELS[app.markType]} />
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
            <InfoRow label="Наименование" value={client.fullNameOrCompanyName} />
            <InfoRow label="Тип" value={CLIENT_TYPE_LABELS[client.type]} />
            <InfoRow label="Контакт" value={client.contactPerson} />
            <InfoRow label="Email" value={client.email} />
            <InfoRow label="Телефон" value={client.phone} />
            <InfoRow label="ИНН" value={client.inn} mono />
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
  label,
  field,
  value,
  multiline,
  onSaved,
}: {
  appId: number;
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
      await api.put(`/applications/${appId}`, { [field]: draft.trim() });
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
    <div className="flex flex-col sm:flex-row sm:items-start gap-1 sm:gap-4 group">
      <span className="text-xs font-medium text-muted-foreground sm:w-32 shrink-0">
        {label}
      </span>
      <span className="text-sm flex-1">{value || "—"}</span>
      <Button
        size="sm"
        variant="ghost"
        className="h-6 px-2 text-[11px] opacity-0 group-hover:opacity-100 transition-opacity"
        onClick={() => setIsEditing(true)}
        data-testid={`edit-${field}`}
      >
        Изменить
      </Button>
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
            <h1 className="text-xl font-bold">{app.markName}</h1>
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

      <Tabs defaultValue="general" className="w-full">
        <TabsList className="w-full flex overflow-x-auto justify-start bg-transparent border-b border-border rounded-none h-auto p-0 gap-0">
          {[
            { value: "general", label: "Общие сведения", icon: Info },
            { value: "source-documents", label: "Исходные документы", icon: Upload },
            { value: "fields", label: "Сверка полей", icon: ClipboardList },
            { value: "legal", label: "Правовой анализ", icon: Shield },
            { value: "recommendations", label: "Рекомендации", icon: Gavel },
            { value: "draft", label: "Черновик заявления", icon: FileSignature },
            { value: "documents", label: "Документы", icon: FileText },
            { value: "history", label: "История", icon: History },
          ].map(tab => (
            <TabsTrigger
              key={tab.value}
              value={tab.value}
              className="flex items-center gap-1.5 px-3 py-2.5 text-xs font-medium rounded-none border-b-2 border-transparent data-[state=active]:border-primary data-[state=active]:bg-transparent data-[state=active]:shadow-none whitespace-nowrap"
              data-testid={`tab-${tab.value}`}
            >
              <tab.icon className="w-3.5 h-3.5" />
              <span className="hidden sm:inline">{tab.label}</span>
            </TabsTrigger>
          ))}
        </TabsList>

        <div className="mt-4">
          <TabsContent value="general">
            <GeneralInfoTab app={app} client={client} onSaved={reload} />
          </TabsContent>
          <TabsContent value="source-documents">
            <SourceDocumentsTab appId={appId} onExtracted={() => setFieldsRefreshKey(k => k + 1)} />
          </TabsContent>
          <TabsContent value="fields">
            <FieldConfirmationTab key={fieldsRefreshKey} appId={appId} />
          </TabsContent>
          <TabsContent value="legal"><LegalAnalysisTab appId={appId} /></TabsContent>
          <TabsContent value="recommendations"><RecommendationsTab appId={appId} /></TabsContent>
          <TabsContent value="draft"><ApplicationDraftTab appId={appId} /></TabsContent>
          <TabsContent value="documents"><DocumentPackagesTab appId={appId} /></TabsContent>
          <TabsContent value="history"><StatusHistoryTab appId={appId} /></TabsContent>
        </div>
      </Tabs>
    </div>
  );
}
