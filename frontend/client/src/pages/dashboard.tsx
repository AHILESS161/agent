import { Link } from "wouter";
import { useCases } from "@/lib/use-cases";
import { useApi, type NotificationsDto } from "@/lib/use-api";
import { AsyncSection } from "@/components/async-states";
import { STATUS_LABELS, STATUS_COLORS } from "@shared/schema";
import { Badge } from "@/components/ui/badge";
import { cn } from "@/lib/utils";

const ATTENTION_STATUSES = new Set([
  "info_requested",
  "classification_review",
  "legal_review_pending",
  "conflict_search_pending",
  "document_generation",
]);

export default function DashboardPage() {
  const cases = useCases();
  const notifications = useApi<NotificationsDto>("/notifications?page=1&page_size=5");
  const today = new Date().toLocaleDateString("ru-RU", {
    day: "numeric",
    month: "long",
    year: "numeric",
  });

  return (
    <div data-testid="dashboard-page">
      <header className="mb-7">
        <h1 className="text-4xl font-semibold leading-none text-foreground lg:text-[46px]">Обзор</h1>
        <p className="mt-3 text-sm text-muted-foreground">{today}</p>
      </header>

      <AsyncSection
        state={cases}
        loadingLabel="Загрузка сводки…"
        emptyTitle="Проектов пока нет"
        emptyHint="Нажмите «Создать», чтобы добавить первый товарный знак."
      >
        {(data) => {
          const apps = data.applications;
          const active = apps.filter((app) => !["closed", "submitted"].includes(app.status));
          const attention = active.filter((app) => ATTENTION_STATUSES.has(app.status));
          const waiting = active.filter((app) => app.status === "info_requested");
          const recent = [...apps]
            .sort((a, b) => new Date(b.updatedAt).getTime() - new Date(a.updatedAt).getTime())
            .slice(0, 6);

          return (
            <>
              <section className="mb-8 rounded-r-[22px] border-y-2 border-r-2 border-primary px-6 py-4">
                <p className="text-2xl leading-tight text-foreground lg:text-[34px]">
                  <strong className="font-semibold">{active.length} активных {projectWord(active.length)}.</strong>{" "}
                  <span>{attention.length} требуют внимания.</span>
                </p>
              </section>

              <section className="mb-9 grid max-w-3xl grid-cols-3">
                {[
                  ["Активные проекты", active.length],
                  ["Требуют внимания", attention.length],
                  ["Ожидают ответа", waiting.length],
                ].map(([label, value], index) => (
                  <div key={String(label)} className={cn("px-6 first:pl-0", index > 0 && "border-l border-border")}>
                    <p className="text-sm text-muted-foreground">{label}</p>
                    <p className="mt-1 text-5xl font-medium leading-none text-foreground">{value}</p>
                  </div>
                ))}
              </section>

              <div className="grid border-t border-border lg:grid-cols-[.95fr_1.25fr]">
                <section className="border-b border-border py-6 lg:border-b-0 lg:border-r lg:pr-8">
                  <h2 className="mb-5 text-base font-semibold">Требуют внимания</h2>
                  <div className="divide-y divide-border">
                    {notifications.isLoading && <p className="py-4 text-sm text-muted-foreground">Загрузка…</p>}
                    {notifications.data?.items.slice(0, 5).map((item, index) => (
                      <div key={item.id} className="flex gap-3 py-3.5 text-sm">
                        <span className={cn("mt-1.5 h-2 w-2 shrink-0 rounded-full", index === 0 ? "bg-red-400" : "bg-primary")} />
                        <div className="min-w-0">
                          <p className="font-medium">{item.title}</p>
                          <p className="mt-1 line-clamp-2 text-xs leading-relaxed text-muted-foreground">{item.message}</p>
                        </div>
                      </div>
                    ))}
                    {!notifications.isLoading && (notifications.data?.items.length ?? 0) === 0 && (
                      <p className="py-4 text-sm text-muted-foreground">Срочных действий нет.</p>
                    )}
                  </div>
                  <Link href="/notifications">
                    <span className="mt-5 inline-block cursor-pointer text-sm font-medium text-primary hover:underline">Все уведомления →</span>
                  </Link>
                </section>

                <section className="py-6 lg:pl-8">
                  <div className="mb-5 flex items-center justify-between">
                    <h2 className="text-base font-semibold">Проекты</h2>
                    <Link href="/applications">
                      <span className="cursor-pointer text-sm text-primary hover:underline">Все проекты</span>
                    </Link>
                  </div>
                  <div className="overflow-x-auto">
                    <table className="w-full min-w-[560px] text-left text-sm">
                      <thead className="text-xs font-normal text-muted-foreground">
                        <tr className="border-b border-border">
                          <th className="pb-3 font-normal">Заявитель</th>
                          <th className="pb-3 font-normal">Товарный знак</th>
                          <th className="pb-3 font-normal">Этап</th>
                          <th className="pb-3 text-right font-normal">Обновлён</th>
                        </tr>
                      </thead>
                      <tbody className="divide-y divide-border">
                        {recent.map((app) => {
                          const client = data.clientsById[app.clientId];
                          return (
                            <tr key={app.id}>
                              <td className="py-3.5 text-muted-foreground">{client?.shortName ?? "—"}</td>
                              <td className="py-3.5">
                                <Link href={`/applications/${app.id}`}>
                                  <span className="cursor-pointer font-medium hover:text-primary">{app.markName}</span>
                                </Link>
                              </td>
                              <td className="py-3.5">
                                <Badge className={cn("whitespace-nowrap text-[10px]", STATUS_COLORS[app.status])}>
                                  {STATUS_LABELS[app.status]}
                                </Badge>
                              </td>
                              <td className="py-3.5 text-right text-xs text-muted-foreground">
                                {new Date(app.updatedAt).toLocaleDateString("ru-RU", { day: "numeric", month: "short" })}
                              </td>
                            </tr>
                          );
                        })}
                      </tbody>
                    </table>
                  </div>
                </section>
              </div>
            </>
          );
        }}
      </AsyncSection>
    </div>
  );
}

function projectWord(value: number) {
  const mod100 = value % 100;
  const mod10 = value % 10;
  if (mod100 >= 11 && mod100 <= 14) return "проектов";
  if (mod10 === 1) return "проект";
  if (mod10 >= 2 && mod10 <= 4) return "проекта";
  return "проектов";
}
