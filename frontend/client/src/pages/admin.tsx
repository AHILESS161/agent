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
import { useState } from "react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import {
  Select, SelectContent, SelectItem, SelectTrigger, SelectValue,
} from "@/components/ui/select";
import { Plus } from "lucide-react";
import { useToast } from "@/hooks/use-toast";
import { useAuth } from "@/lib/auth";
import { api, ApiError } from "@/lib/api";

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
  const { toast } = useToast();
  const { user: me } = useAuth();
  const state = useApi<Paginated<UserDto>>("/users?page=1&page_size=100");
  const [busy, setBusy] = useState<number | null>(null);
  const [isAdding, setIsAdding] = useState(false);

  const fail = (e: unknown, title: string) =>
    toast({
      title,
      description: e instanceof ApiError ? e.message : "Неизвестная ошибка",
      variant: "destructive",
    });

  const changeRole = async (user: UserDto, role: string) => {
    setBusy(user.id);
    try {
      await api.put(`/users/${user.id}`, { role });
      toast({
        title: `Роль изменена: ${user.full_name || user.email}`,
        description: `Теперь — ${ROLE_LABELS[role as UserRole] ?? role}.`,
      });
      state.reload();
    } catch (e) {
      fail(e, "Не удалось изменить роль");
    } finally {
      setBusy(null);
    }
  };

  /** Доступ отключается, а не стирается: пользователь связан
      с делами и записями журнала, и удалить его — значит порвать
      историю работы. */
  const setActive = async (user: UserDto, active: boolean) => {
    setBusy(user.id);
    try {
      if (active) {
        await api.put(`/users/${user.id}`, { is_active: true });
      } else {
        await api.delete(`/users/${user.id}`);
      }
      toast({
        title: active
          ? `Доступ восстановлен: ${user.full_name || user.email}`
          : `Доступ отключён: ${user.full_name || user.email}`,
      });
      state.reload();
    } catch (e) {
      fail(e, "Не удалось изменить доступ");
    } finally {
      setBusy(null);
    }
  };

  return (
    <AsyncSection
      state={state}
      loadingLabel="Загрузка пользователей…"
      emptyTitle="Пользователей нет"
    >
      {(data) => (
        <Card className="border border-card-border overflow-hidden">
          <CardHeader className="pb-2 flex flex-row items-center justify-between gap-2">
            <CardTitle className="text-sm font-semibold">
              Пользователи ({data.total})
            </CardTitle>
            <Button size="sm" onClick={() => setIsAdding(true)} data-testid="add-user">
              <Plus className="w-3.5 h-3.5 mr-1.5" />
              Добавить
            </Button>
          </CardHeader>
          <CardContent className="p-0">
            {isAdding && (
              <div className="p-3 border-b border-border">
                <NewUserForm
                  onCancel={() => setIsAdding(false)}
                  onCreated={() => {
                    setIsAdding(false);
                    state.reload();
                  }}
                />
              </div>
            )}
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>Пользователь</TableHead>
                  <TableHead className="hidden md:table-cell">Email</TableHead>
                  <TableHead>Роль</TableHead>
                  <TableHead className="w-24">Статус</TableHead>
                  <TableHead className="w-32"></TableHead>
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
                      <Select
                        value={user.role}
                        onValueChange={(v) => void changeRole(user, v)}
                        disabled={busy === user.id || user.id === me?.id}
                      >
                        <SelectTrigger
                          className="h-7 w-40 text-[11px]"
                          data-testid={`role-${user.id}`}
                        >
                          <SelectValue />
                        </SelectTrigger>
                        <SelectContent>
                          {(Object.keys(ROLE_LABELS) as UserRole[]).map((role) => (
                            <SelectItem key={role} value={role} className="text-xs">
                              {ROLE_LABELS[role]}
                            </SelectItem>
                          ))}
                        </SelectContent>
                      </Select>
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
                    <TableCell>
                      {/* Свой доступ отключить нельзя: администратор
                          заблокировал бы сам себя. */}
                      {user.id !== me?.id && (
                        <Button
                          size="sm"
                          variant="ghost"
                          className="h-7 text-[11px]"
                          disabled={busy === user.id}
                          onClick={() => void setActive(user, !user.is_active)}
                          data-testid={`toggle-user-${user.id}`}
                        >
                          {user.is_active ? "Отключить" : "Включить"}
                        </Button>
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

/**
 * Создание пользователя.
 *
 * Регистрация закрыта: заводит учётные записи только администратор.
 * Иначе эндпоинт принимает поле роли, и любой желающий назначил бы
 * себе права администратора.
 */
function NewUserForm({
  onCreated,
  onCancel,
}: {
  onCreated: () => void;
  onCancel: () => void;
}) {
  const { toast } = useToast();
  const [email, setEmail] = useState("");
  const [fullName, setFullName] = useState("");
  const [role, setRole] = useState<UserRole>("lawyer");
  const [password, setPassword] = useState("");
  const [isSaving, setIsSaving] = useState(false);

  const create = async () => {
    if (password.length < 8) {
      toast({
        title: "Пароль слишком короткий",
        description: "Не менее 8 символов.",
        variant: "destructive",
      });
      return;
    }

    setIsSaving(true);
    try {
      await api.post("/auth/register", {
        email: email.trim(),
        password,
        full_name: fullName.trim() || null,
        role,
      });
      toast({
        title: `Пользователь создан: ${fullName || email}`,
        description: "Передайте ему пароль — сменить его можно в профиле.",
      });
      onCreated();
    } catch (e) {
      toast({
        title: "Не удалось создать пользователя",
        description: e instanceof ApiError ? e.message : "Неизвестная ошибка",
        variant: "destructive",
      });
    } finally {
      setIsSaving(false);
    }
  };

  return (
    <div className="space-y-3">
      <div className="grid gap-3 sm:grid-cols-2">
        <div className="space-y-1">
          <Label className="text-xs font-medium">ФИО</Label>
          <Input
            autoFocus
            value={fullName}
            onChange={(e) => setFullName(e.target.value)}
            placeholder="Иванова Елена Викторовна"
            className="h-8 text-sm"
            data-testid="new-user-name"
          />
        </div>
        <div className="space-y-1">
          <Label className="text-xs font-medium">Почта</Label>
          <Input
            type="email"
            value={email}
            onChange={(e) => setEmail(e.target.value)}
            placeholder="ivanova@example.ru"
            className="h-8 text-sm"
            data-testid="new-user-email"
          />
        </div>
        <div className="space-y-1">
          <Label className="text-xs font-medium">Роль</Label>
          <Select value={role} onValueChange={(v) => setRole(v as UserRole)}>
            <SelectTrigger className="h-8 text-sm" data-testid="new-user-role">
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              {(Object.keys(ROLE_LABELS) as UserRole[]).map((key) => (
                <SelectItem key={key} value={key} className="text-sm">
                  {ROLE_LABELS[key]}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        </div>
        <div className="space-y-1">
          <Label className="text-xs font-medium">Временный пароль</Label>
          <Input
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            placeholder="не менее 8 символов"
            className="h-8 text-sm"
            data-testid="new-user-password"
          />
        </div>
      </div>

      <div className="flex gap-2">
        <Button
          size="sm"
          disabled={isSaving || !email.trim() || !password}
          onClick={() => void create()}
          data-testid="save-new-user"
        >
          Создать
        </Button>
        <Button size="sm" variant="ghost" onClick={onCancel}>
          Отмена
        </Button>
      </div>
    </div>
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
