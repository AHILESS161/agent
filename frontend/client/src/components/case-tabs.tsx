/**
 * Вкладки карточки дела, работающие с реальным API.
 *
 * Заменяют разделы, которые читали демонстрационные данные. Каждая
 * вкладка честно показывает три состояния: загрузка, пусто (шаг ещё
 * не выполнялся) и ошибка с возможностью повторить.
 */

import { useState } from "react";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Separator } from "@/components/ui/separator";
import { useToast } from "@/hooks/use-toast";
import { AsyncSection } from "@/components/async-states";
import { AiDisclaimer, DemoModeBadge } from "@/components/ai-disclaimer";
import { api, ApiError } from "@/lib/api";
import {
  useApi,
  type ClassesDto,
  type CompletenessDto,
  type ConflictsDto,
  type DocumentPackagesDto,
  type LegalReviewDto,
  type StatusDto,
} from "@/lib/use-api";
import { STATUS_LABELS, type ApplicationStatus } from "@shared/schema";
import { cn } from "@/lib/utils";
import {
  AlertTriangle,
  Check,
  CheckCircle2,
  Download,
  Loader2,
  Sparkles,
  Search,
} from "lucide-react";

const RISK_STYLES: Record<string, string> = {
  low: "bg-emerald-500/15 text-emerald-700 dark:text-emerald-400",
  medium: "bg-amber-500/15 text-amber-700 dark:text-amber-500",
  high: "bg-orange-500/15 text-orange-700 dark:text-orange-400",
  critical: "bg-red-500/15 text-red-700 dark:text-red-400",
};

const RISK_LABELS: Record<string, string> = {
  low: "Низкий",
  medium: "Средний",
  high: "Высокий",
  critical: "Критический",
};

// ---------------------------------------------------------------------------
// Полнота данных
// ---------------------------------------------------------------------------

export function CompletenessTab({ appId }: { appId: number }) {
  const state = useApi<CompletenessDto>(`/applications/${appId}/validate`, {
    method: "POST",
  });

  return (
    <AsyncSection
      state={state}
      loadingLabel="Проверка полноты данных…"
      emptyTitle="Проверка не выполнена"
      emptyHint="Не удалось получить результат проверки полноты."
    >
      {(data) => (
        <div className="space-y-3">
          <Card>
            <CardContent className="p-3 flex items-center gap-2">
              {data.is_complete ? (
                <>
                  <CheckCircle2 className="w-4 h-4 text-emerald-600" />
                  <span className="text-sm font-medium">
                    Данных достаточно для текущего этапа
                  </span>
                </>
              ) : (
                <>
                  <AlertTriangle className="w-4 h-4 text-amber-600" />
                  <span className="text-sm font-medium">
                    Требуется дозаполнить данные
                  </span>
                </>
              )}
              <Badge variant="secondary" className="ml-auto text-[10px]">
                этап: {data.stage}
              </Badge>
            </CardContent>
          </Card>

          {data.blocking_issues.length > 0 && (
            <IssueList
              title="Блокирующие"
              tone="destructive"
              issues={data.blocking_issues}
            />
          )}
          {data.non_blocking_issues.length > 0 && (
            <IssueList
              title="Некритичные"
              tone="muted"
              issues={data.non_blocking_issues}
            />
          )}
          {data.blocking_issues.length === 0 &&
            data.non_blocking_issues.length === 0 && (
              <p className="text-xs text-muted-foreground">
                Замечаний нет.
              </p>
            )}
        </div>
      )}
    </AsyncSection>
  );
}

function IssueList({
  title,
  issues,
  tone,
}: {
  title: string;
  issues: { field: string; message: string }[];
  tone: "destructive" | "muted";
}) {
  return (
    <Card>
      <CardHeader className="pb-2">
        <CardTitle className="text-sm font-semibold">
          {title} ({issues.length})
        </CardTitle>
      </CardHeader>
      <CardContent className="space-y-1.5">
        {issues.map((issue, index) => (
          <div key={`${issue.field}-${index}`} className="flex items-start gap-2">
            <span
              className={cn(
                "mt-1 h-1.5 w-1.5 shrink-0 rounded-full",
                tone === "destructive" ? "bg-destructive" : "bg-muted-foreground",
              )}
            />
            <div className="min-w-0">
              <p className="text-xs">{issue.message}</p>
              <p className="text-[10px] font-mono text-muted-foreground">
                {issue.field}
              </p>
            </div>
          </div>
        ))}
      </CardContent>
    </Card>
  );
}

function SummaryCard({ title, text }: { title: string; text: string }) {
  return (
    <Card>
      <CardHeader className="pb-2">
        <CardTitle className="text-sm font-semibold">{title}</CardTitle>
      </CardHeader>
      <CardContent>
        <p className="text-xs leading-relaxed">{text}</p>
      </CardContent>
    </Card>
  );
}

// ---------------------------------------------------------------------------
// Документы
// ---------------------------------------------------------------------------

export function DocumentPackagesTab({ appId }: { appId: number }) {
  const { toast } = useToast();
  const state = useApi<DocumentPackagesDto>(`/applications/${appId}/documents`);

  const download = async (id: number) => {
    try {
      await api.download(`/applications/${appId}/documents/${id}/download`, `package-${id}.docx`);
    } catch (e) {
      toast({
        title: "Не удалось скачать документ",
        description:
          e instanceof ApiError ? e.message : "Экспорт пока недоступен",
        variant: "destructive",
      });
    }
  };

  return (
    <AsyncSection
      state={state}
      loadingLabel="Загрузка пакетов документов…"
      emptyTitle="Документы не сформированы"
      emptyHint="Черновой пакет формируется после подтверждения критичных полей дела."
    >
      {(data) =>
        data.packages.length === 0 ? (
          <div className="space-y-3">
            <p className="text-xs text-muted-foreground">
              Пакетов документов пока нет. Черновик заявления формируется
              только из подтверждённых специалистом полей.
            </p>
            <AiDisclaimer compact />
          </div>
        ) : (
          <div className="space-y-2">
            {data.packages.map((pkg) => (
              <Card key={pkg.id}>
                <CardContent className="p-3 flex items-center justify-between gap-3">
                  <div className="min-w-0">
                    <p className="text-sm font-medium">Пакет №{pkg.id}</p>
                    <p className="text-[11px] text-muted-foreground">
                      статус: {pkg.status}
                      {pkg.created_at
                        ? ` · ${new Date(pkg.created_at).toLocaleDateString("ru-RU")}`
                        : ""}
                    </p>
                  </div>
                  <Button
                    size="sm"
                    variant="outline"
                    onClick={() => void download(pkg.id)}
                  >
                    <Download className="w-3.5 h-3.5 mr-1.5" />
                    Скачать
                  </Button>
                </CardContent>
              </Card>
            ))}
          </div>
        )
      }
    </AsyncSection>
  );
}

// ---------------------------------------------------------------------------
// История статусов
// ---------------------------------------------------------------------------

export function StatusHistoryTab({ appId }: { appId: number }) {
  const state = useApi<StatusDto>(`/applications/${appId}/status`);

  return (
    <AsyncSection
      state={state}
      loadingLabel="Загрузка истории…"
      emptyTitle="История недоступна"
    >
      {(data) => (
        <div className="space-y-3">
          <Card>
            <CardContent className="p-3">
              <div className="flex flex-wrap items-center gap-2">
                <span className="text-sm font-medium">Текущий статус:</span>
                <Badge className="text-[10px]">
                  {STATUS_LABELS[data.status as ApplicationStatus] ?? data.status}
                </Badge>
              </div>
              {data.allowed_transitions.length > 0 && (
                <p className="text-[11px] text-muted-foreground mt-1.5">
                  Возможные переходы:{" "}
                  {data.allowed_transitions
                    .map((s) => STATUS_LABELS[s as ApplicationStatus] ?? s)
                    .join(", ")}
                </p>
              )}
            </CardContent>
          </Card>

          {data.status_events.length === 0 ? (
            <p className="text-xs text-muted-foreground">
              Событий по делу пока не зафиксировано.
            </p>
          ) : (
            <div className="space-y-2">
              {data.status_events.map((event, index) => (
                <div
                  key={event.id ?? index}
                  className="flex gap-3 border-l-2 border-border pl-3"
                >
                  <div className="min-w-0">
                    <p className="text-xs font-medium">
                      {event.status
                        ? STATUS_LABELS[event.status as ApplicationStatus] ?? event.status
                        : event.event_type ?? "Событие"}
                    </p>
                    {event.description && (
                      <p className="text-[11px] text-muted-foreground">
                        {event.description}
                      </p>
                    )}
                    {event.created_at && (
                      <p className="text-[10px] text-muted-foreground">
                        {new Date(event.created_at).toLocaleString("ru-RU")}
                      </p>
                    )}
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>
      )}
    </AsyncSection>
  );
}

// ---------------------------------------------------------------------------
// Рекомендации
// ---------------------------------------------------------------------------

export function RecommendationsTab({ appId }: { appId: number }) {
  const state = useApi<Record<string, any>>(`/applications/${appId}/recommendation`);

  return (
    <AsyncSection
      state={state}
      loadingLabel="Загрузка рекомендаций…"
      emptyTitle="Рекомендации не сформированы"
      emptyHint="Итоговое заключение готовится после правового анализа и поиска конфликтов."
    >
      {(data) => (
        <div className="space-y-3">
          <AiDisclaimer />
          {data.summary && (
            <SummaryCard title="Краткий вывод" text={String(data.summary)} />
          )}
          {Array.isArray(data.key_findings) && data.key_findings.length > 0 && (
            <Card>
              <CardHeader className="pb-2">
                <CardTitle className="text-sm font-semibold">
                  Ключевые выводы
                </CardTitle>
              </CardHeader>
              <CardContent className="space-y-1">
                {data.key_findings.map((item: string, index: number) => (
                  <p key={index} className="text-xs">
                    • {item}
                  </p>
                ))}
              </CardContent>
            </Card>
          )}
          {data.recommended_action && (
            <Card>
              <CardContent className="p-3 text-xs">
                Рекомендуемое действие:{" "}
                <span className="font-medium">{String(data.recommended_action)}</span>
              </CardContent>
            </Card>
          )}
        </div>
      )}
    </AsyncSection>
  );
}
