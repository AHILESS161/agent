import { useAuth } from "@/lib/auth";
import { Link } from "wouter";
import { useCases } from "@/lib/use-cases";
import { useApi, type NotificationsDto } from "@/lib/use-api";
import { AsyncSection } from "@/components/async-states";
import {
  STATUS_LABELS,
  STATUS_COLORS,
  ROLE_LABELS,
  type ApplicationStatus,
} from "@shared/schema";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Bell, FileText, Plus, TrendingUp } from "lucide-react";
import { cn } from "@/lib/utils";

/** Группировка состояний дела для сводки. */
const STATUS_GROUPS: { label: string; statuses: ApplicationStatus[]; color: string }[] = [
  {
    label: "Черновик / Сбор данных",
    statuses: ["draft", "info_requested", "info_received"],
    color: "bg-slate-400",
  },
  {
    label: "Классификация",
    statuses: [
      "classification_pending",
      "classification_review",
      "classification_approved",
    ],
    color: "bg-cyan-500",
  },
  {
    label: "Правовой анализ",
    statuses: [
      "legal_review_pending",
      "legal_review_in_progress",
      "legal_review_done",
    ],
    color: "bg-blue-500",
  },
  {
    label: "Поиск конфликтов",
    statuses: [
      "conflict_search_pending",
      "conflict_search_in_progress",
      "conflict_search_done",
    ],
    color: "bg-violet-500",
  },
  {
    label: "Заключение и документы",
    statuses: [
      "memo_generation",
      "memo_approved",
      "document_generation",
      "document_approved",
    ],
    color: "bg-amber-500",
  },
  {
    label: "Подана / Закрыта",
    statuses: ["submitted", "closed"],
    color: "bg-emerald-500",
  },
];

function displayName(user: { fullName: string; preferredName?: string | null } | null): string {
  if (!user) return "";
  const preferred = user.preferredName?.trim();
  if (preferred) return preferred;

  const parts = user.fullName.trim().split(/\s+/);
  // «Фамилия Имя Отчество» → имя; одно слово или адрес почты — как есть.
  return parts.length >= 2 ? parts[1] : parts[0];
}

function greeting(): string {
  const hour = new Date().getHours();
  if (hour < 6) return "Доброй ночи";
  if (hour < 12) return "Доброе утро";
  if (hour < 18) return "Добрый день";
  return "Добрый вечер";
}

export default function DashboardPage() {
  const { user } = useAuth();
  const cases = useCases();
  const notifications = useApi<NotificationsDto>("/notifications?page=1&page_size=5");

  // ФИО хранится как «Фамилия Имя Отчество», поэтому первое слово —
  // это фамилия, и приветствие по нему звучит казённо. Берём имя,
  // а если человек задал в профиле, как к нему обращаться, — его.
  const shortName = displayName(user);

  return (
    <div className="space-y-4" data-testid="dashboard-page">
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-2">
        <div>
          <h1 className="text-xl font-bold">
            {greeting()}
            {shortName ? `, ${shortName}` : ""}
          </h1>
          <p className="text-sm text-muted-foreground">
            {user ? ROLE_LABELS[user.role] : ""} ·{" "}
            {new Date().toLocaleDateString("ru-RU", {
              weekday: "long",
              day: "numeric",
              month: "long",
              year: "numeric",
            })}
          </p>
        </div>
        <Link href="/applications/new">
          <Button size="sm" data-testid="button-new-application">
            <Plus className="w-4 h-4 mr-1.5" />
            Новое дело
          </Button>
        </Link>
      </div>

      <AsyncSection
        state={cases}
        loadingLabel="Загрузка сводки…"
        emptyTitle="Дел пока нет"
        emptyHint="Создайте первое дело, чтобы начать работу."
      >
        {(data) => {
          const apps = data.applications;
          const active = apps.filter(
            (a) => a.status !== "closed" && a.status !== "submitted",
          );
          const submitted = apps.filter((a) => a.status === "submitted");
          const closed = apps.filter((a) => a.status === "closed");

          const stats = [
            { label: "Всего дел", value: apps.length, icon: FileText },
            { label: "В работе", value: active.length, icon: TrendingUp },
            { label: "Поданы", value: submitted.length, icon: FileText },
            { label: "Закрыты", value: closed.length, icon: FileText },
          ];

          return (
            <>
              <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
                {stats.map((stat) => (
                  <Card key={stat.label} className="border border-card-border">
                    <CardContent className="p-4 flex items-center gap-3">
                      <div className="rounded-md bg-primary/10 p-2">
                        <stat.icon className="w-4 h-4 text-primary" />
                      </div>
                      <div>
                        <p className="text-2xl font-bold">{stat.value}</p>
                        <p className="text-xs text-muted-foreground mt-0.5">
                          {stat.label}
                        </p>
                      </div>
                    </CardContent>
                  </Card>
                ))}
              </div>

              <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
                <Card className="border border-card-border">
                  <CardHeader className="pb-2">
                    <CardTitle className="text-sm font-semibold">
                      Распределение по этапам
                    </CardTitle>
                  </CardHeader>
                  <CardContent className="space-y-2">
                    {STATUS_GROUPS.map((group) => {
                      const count = apps.filter((a) =>
                        group.statuses.includes(a.status),
                      ).length;
                      const percent = apps.length
                        ? Math.round((count / apps.length) * 100)
                        : 0;
                      return (
                        <div key={group.label}>
                          <div className="flex items-center justify-between text-xs">
                            <span>{group.label}</span>
                            <span className="text-muted-foreground">{count}</span>
                          </div>
                          <div className="mt-1 h-1.5 w-full rounded-full bg-muted">
                            <div
                              className={cn("h-1.5 rounded-full", group.color)}
                              style={{ width: `${percent}%` }}
                            />
                          </div>
                        </div>
                      );
                    })}
                  </CardContent>
                </Card>

                <Card className="border border-card-border">
                  <CardHeader className="pb-2">
                    <CardTitle className="text-sm font-semibold">
                      Последние дела
                    </CardTitle>
                  </CardHeader>
                  <CardContent className="space-y-2">
                    {apps.slice(0, 6).map((app) => {
                      const client = data.clientsById[app.clientId];
                      return (
                        <div
                          key={app.id}
                          className="flex items-center justify-between gap-2"
                        >
                          <div className="min-w-0">
                            <Link href={`/applications/${app.id}`}>
                              <span className="text-sm font-medium hover:text-primary cursor-pointer">
                                {app.markName}
                              </span>
                            </Link>
                            <p className="text-[11px] text-muted-foreground">
                              #{app.id}
                              {client ? ` · ${client.shortName}` : ""}
                            </p>
                          </div>
                          <Badge
                            className={cn(
                              "text-[10px] whitespace-nowrap",
                              STATUS_COLORS[app.status],
                            )}
                          >
                            {STATUS_LABELS[app.status]}
                          </Badge>
                        </div>
                      );
                    })}
                  </CardContent>
                </Card>
              </div>
            </>
          );
        }}
      </AsyncSection>

      <Card className="border border-card-border">
        <CardHeader className="pb-2">
          <CardTitle className="text-sm font-semibold flex items-center gap-1.5">
            <Bell className="w-3.5 h-3.5" />
            Уведомления
          </CardTitle>
        </CardHeader>
        <CardContent className="space-y-2">
          {notifications.isLoading && (
            <p className="text-xs text-muted-foreground">Загрузка…</p>
          )}
          {!notifications.isLoading &&
            (notifications.data?.items.length ?? 0) === 0 && (
              <p className="text-xs text-muted-foreground">Новых уведомлений нет.</p>
            )}
          {notifications.data?.items.map((item) => (
            <div key={item.id} className="border-b border-border pb-2 last:border-0">
              <p className="text-xs font-medium">{item.title}</p>
              <p className="text-[11px] text-muted-foreground">{item.message}</p>
            </div>
          ))}
        </CardContent>
      </Card>
    </div>
  );
}
