import { useApi, type AdminStatsDto, type UserDto, type Paginated } from "@/lib/use-api";
import { AsyncSection } from "@/components/async-states";
import { ROLE_LABELS, type UserRole } from "@shared/schema";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import {
  Users,
  Activity,
  Database,
  FileText,
  CheckCircle,
  XCircle,
  Server,
} from "lucide-react";
import { cn } from "@/lib/utils";

function SystemStats() {
  const state = useApi<AdminStatsDto>("/admin/stats");

  return (
    <AsyncSection
      state={state}
      loadingLabel="Загрузка статистики…"
      emptyTitle="Статистика недоступна"
    >
      {(stats) => {
        const cards = [
          { label: "Пользователей", value: stats.users.total, icon: Users },
          { label: "Дел", value: stats.applications.total, icon: FileText },
          { label: "Клиентов", value: stats.clients.total, icon: Database },
          {
            label: "Правовых анализов",
            value: stats.legal_reviews.total,
            icon: Activity,
          },
        ];

        return (
          <div className="space-y-4">
            <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
              {cards.map((card) => (
                <Card key={card.label} className="border border-card-border">
                  <CardContent className="p-4 flex items-center gap-3">
                    <div className="rounded-md bg-primary/10 p-2">
                      <card.icon className="w-4 h-4 text-primary" />
                    </div>
                    <div>
                      <p className="text-xl font-bold">{card.value}</p>
                      <p className="text-xs text-muted-foreground">{card.label}</p>
                    </div>
                  </CardContent>
                </Card>
              ))}
            </div>

            <Card className="border border-card-border">
              <CardHeader className="pb-2">
                <CardTitle className="text-sm font-semibold">
                  Дела по состоянию
                </CardTitle>
              </CardHeader>
              <CardContent className="grid grid-cols-3 gap-3 text-sm">
                <Stat label="Черновики" value={stats.applications.draft} />
                <Stat label="В работе" value={stats.applications.in_progress} />
                <Stat label="Поданы" value={stats.applications.submitted} />
              </CardContent>
            </Card>

            <Card className="border border-card-border">
              <CardHeader className="pb-2">
                <CardTitle className="text-sm font-semibold">
                  Результаты обработки
                </CardTitle>
              </CardHeader>
              <CardContent className="grid grid-cols-2 sm:grid-cols-4 gap-3 text-sm">
                <Stat label="Классы МКТУ" value={stats.class_suggestions.total} />
                <Stat label="Конфликты" value={stats.conflict_results.total} />
                <Stat label="Пакеты документов" value={stats.document_packages.total} />
                <Stat label="Подачи" value={stats.submissions.total} />
              </CardContent>
            </Card>
          </div>
        );
      }}
    </AsyncSection>
  );
}

function Stat({ label, value }: { label: string; value: number }) {
  return (
    <div>
      <p className="text-lg font-semibold">{value}</p>
      <p className="text-xs text-muted-foreground">{label}</p>
    </div>
  );
}

function UsersTable() {
  const state = useApi<Paginated<UserDto>>("/users?page=1&page_size=100");

  return (
    <AsyncSection
      state={state}
      loadingLabel="Загрузка пользователей…"
      emptyTitle="Пользователей нет"
    >
      {(data) => (
        <Card className="border border-card-border overflow-hidden">
          <CardHeader className="pb-2">
            <CardTitle className="text-sm font-semibold">
              Пользователи ({data.total})
            </CardTitle>
          </CardHeader>
          <CardContent className="p-0">
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>Пользователь</TableHead>
                  <TableHead className="hidden md:table-cell">Email</TableHead>
                  <TableHead>Роль</TableHead>
                  <TableHead className="w-24">Статус</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {data.items.map((user) => (
                  <TableRow key={user.id} data-testid={`user-row-${user.id}`}>
                    <TableCell className="text-sm font-medium">
                      {user.full_name || user.email}
                    </TableCell>
                    <TableCell className="hidden md:table-cell text-sm text-muted-foreground">
                      {user.email}
                    </TableCell>
                    <TableCell>
                      <Badge variant="secondary" className="text-[10px]">
                        {ROLE_LABELS[user.role as UserRole] ?? user.role}
                      </Badge>
                    </TableCell>
                    <TableCell>
                      {user.is_active ? (
                        <span className="flex items-center gap-1 text-xs text-emerald-600">
                          <CheckCircle className="w-3.5 h-3.5" /> активен
                        </span>
                      ) : (
                        <span className="flex items-center gap-1 text-xs text-muted-foreground">
                          <XCircle className="w-3.5 h-3.5" /> отключён
                        </span>
                      )}
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </CardContent>
        </Card>
      )}
    </AsyncSection>
  );
}

function PromptsTable() {
  const state = useApi<{ prompts?: unknown[]; items?: unknown[] }>("/admin/prompts");

  return (
    <AsyncSection
      state={state}
      loadingLabel="Загрузка промптов…"
      emptyTitle="Промпты недоступны"
    >
      {(data) => {
        const items = (data.prompts ?? data.items ?? []) as Record<string, any>[];
        return (
          <Card className="border border-card-border">
            <CardHeader className="pb-2">
              <CardTitle className="text-sm font-semibold">
                Реестр промптов ({items.length})
              </CardTitle>
            </CardHeader>
            <CardContent className="space-y-1.5">
              {items.length === 0 ? (
                <p className="text-xs text-muted-foreground">Промптов нет.</p>
              ) : (
                items.map((item, index) => (
                  <div
                    key={String(item.prompt_id ?? item.id ?? index)}
                    className="flex items-center justify-between gap-2 border-b border-border pb-1.5 last:border-0"
                  >
                    <span className="text-xs font-mono">
                      {String(item.prompt_id ?? item.id ?? "—")}
                    </span>
                    {item.version && (
                      <Badge variant="outline" className="text-[10px]">
                        v{String(item.version)}
                      </Badge>
                    )}
                  </div>
                ))
              )}
            </CardContent>
          </Card>
        );
      }}
    </AsyncSection>
  );
}

export default function AdminPage() {
  return (
    <div className="space-y-4" data-testid="admin-page">
      <div className="flex items-center gap-2">
        <Server className="w-5 h-5 text-primary" />
        <h1 className="text-xl font-bold">Администрирование</h1>
      </div>

      <Tabs defaultValue="stats" className="w-full">
        <TabsList>
          <TabsTrigger value="stats" data-testid="tab-admin-stats">
            Статистика
          </TabsTrigger>
          <TabsTrigger value="users" data-testid="tab-admin-users">
            Пользователи
          </TabsTrigger>
          <TabsTrigger value="prompts" data-testid="tab-admin-prompts">
            Промпты
          </TabsTrigger>
        </TabsList>

        <div className="mt-4">
          <TabsContent value="stats">
            <SystemStats />
          </TabsContent>
          <TabsContent value="users">
            <UsersTable />
          </TabsContent>
          <TabsContent value="prompts">
            <PromptsTable />
          </TabsContent>
        </div>
      </Tabs>
    </div>
  );
}
