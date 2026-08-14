import { useState, useMemo } from "react";
import { Link, useSearch } from "wouter";
import { useAuth } from "@/lib/auth";
import { useCases } from "@/lib/use-cases";
import {
  STATUS_LABELS, STATUS_COLORS, MARK_TYPE_LABELS,
  PRIORITY_LABELS, PRIORITY_COLORS,
  type ApplicationStatus, type CasePriority,
} from "@shared/schema";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { Plus, Search, Filter, Eye, Pencil, Trash2, Loader2, AlertCircle, RefreshCw } from "lucide-react";
import { useToast } from "@/hooks/use-toast";
import { api, ApiError } from "@/lib/api";
import { cn } from "@/lib/utils";

export default function ApplicationsListPage() {
  const { user } = useAuth();
  const routeSearch = useSearch();
  const [search, setSearch] = useState(() => new URLSearchParams(routeSearch).get("search") ?? "");
  const [statusFilter, setStatusFilter] = useState<string>("all");

  const { data, isLoading, error, reload } = useCases();
  const applications = data?.applications ?? [];
  const clientsById = data?.clientsById ?? {};

  // Клиент видит только свои дела; остальные роли — все дела,
  // фильтрация по исполнителю доступна вручную.
  const baseApps = useMemo(() => {
    if (!user) return [];
    if (user.role === "client") {
      return applications.filter(app => app.clientId === user.id);
    }
    return applications;
  }, [user, applications]);

  const filtered = useMemo(() => {
    return baseApps.filter(app => {
      if (statusFilter !== "all" && app.status !== statusFilter) return false;
      if (search) {
        const q = search.toLowerCase();
        const client = clientsById[app.clientId];
        return (
          app.markName.toLowerCase().includes(q) ||
          app.id.toString().includes(q) ||
          (client?.shortName ?? "").toLowerCase().includes(q)
        );
      }
      return true;
    });
  }, [baseApps, search, statusFilter, clientsById]);

  const statusOptions: ApplicationStatus[] = [...new Set(baseApps.map(a => a.status))];

  if (isLoading) {
    return (
      <div className="flex items-center justify-center gap-2 py-16 text-muted-foreground">
        <Loader2 className="w-4 h-4 animate-spin" />
        <span className="text-sm">Загрузка заявок…</span>
      </div>
    );
  }

  if (error) {
    return (
      <div className="flex items-start gap-2 rounded-md border border-destructive/40 bg-destructive/10 px-3 py-2">
        <AlertCircle className="w-4 h-4 shrink-0 mt-0.5 text-destructive" />
        <p className="flex-1 text-sm" data-testid="applications-error">{error}</p>
        <Button variant="ghost" size="sm" onClick={reload}>
          <RefreshCw className="w-3.5 h-3.5 mr-1.5" />
          Повторить
        </Button>
      </div>
    );
  }

  return (
    <div className="space-y-4" data-testid="applications-list-page">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-4xl font-semibold">Товарные знаки</h1>
          <p className="mt-2 text-sm text-muted-foreground">Все проекты и этапы регистрации</p>
        </div>
        {user?.role !== "client" && (
          <Link href="/intake">
            <Button size="sm" data-testid="button-new-application">
              <Plus className="w-4 h-4 mr-1.5" />
              Создать проект
            </Button>
          </Link>
        )}
      </div>

      <Card className="border border-card-border">
        <CardContent className="p-4">
          <div className="flex flex-col sm:flex-row gap-3">
            <div className="relative flex-1">
              <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-muted-foreground" />
              <Input
                placeholder="Поиск по названию, номеру, клиенту..."
                value={search}
                onChange={e => setSearch(e.target.value)}
                className="pl-9"
                data-testid="input-search-applications"
              />
            </div>
            <Select value={statusFilter} onValueChange={setStatusFilter}>
              <SelectTrigger className="w-full sm:w-56" data-testid="select-status-filter">
                <Filter className="w-3.5 h-3.5 mr-2 text-muted-foreground" />
                <SelectValue placeholder="Все статусы" />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="all">Все статусы</SelectItem>
                {statusOptions.map(s => (
                  <SelectItem key={s} value={s}>{STATUS_LABELS[s]}</SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>
        </CardContent>
      </Card>

      <Card className="border border-card-border">
        <div className="overflow-x-auto">
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead className="w-16">№</TableHead>
                <TableHead>Обозначение</TableHead>
                <TableHead className="hidden md:table-cell">Клиент</TableHead>
                <TableHead className="hidden lg:table-cell">Тип</TableHead>
                <TableHead>Статус</TableHead>
                <TableHead>Приоритет</TableHead>
                <TableHead className="hidden md:table-cell">Исполнитель</TableHead>
                <TableHead className="hidden lg:table-cell">Обновлено</TableHead>
                <TableHead className="w-20"></TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {filtered.map(app => {
                const client = clientsById[app.clientId];
                return (
                  <TableRow key={app.id} data-testid={`app-table-row-${app.id}`}>
                    <TableCell className="font-mono text-xs text-muted-foreground">#{app.id}</TableCell>
                    <TableCell>
                      <div>
                        <Link href={`/applications/${app.id}`}>
                          <span className="font-medium text-sm hover:text-primary cursor-pointer">{app.markName}</span>
                        </Link>
                      </div>
                    </TableCell>
                    <TableCell className="hidden md:table-cell text-sm text-muted-foreground">
                      {client?.shortName}
                    </TableCell>
                    <TableCell className="hidden lg:table-cell text-sm text-muted-foreground">
                      {MARK_TYPE_LABELS[app.markType]}
                    </TableCell>
                    <TableCell>
                      <Badge className={cn("text-[10px] whitespace-nowrap", STATUS_COLORS[app.status])}>
                        {STATUS_LABELS[app.status]}
                      </Badge>
                    </TableCell>
                    <TableCell>
                      <PrioritySelect
                        appId={app.id}
                        value={app.priority}
                        onChanged={reload}
                      />
                    </TableCell>
                    <TableCell className="hidden md:table-cell text-sm text-muted-foreground">
                      {app.assigneeId ? `Пользователь #${app.assigneeId}` : "—"}
                    </TableCell>
                    <TableCell className="hidden lg:table-cell text-xs text-muted-foreground">
                      {new Date(app.updatedAt).toLocaleDateString("ru-RU")}
                    </TableCell>
                    <TableCell>
                      <div className="flex items-center gap-1">
                        <Link href={`/applications/${app.id}`}>
                          <Button variant="ghost" size="icon" className="h-7 w-7" data-testid={`view-app-${app.id}`}>
                            <Eye className="w-3.5 h-3.5" />
                          </Button>
                        </Link>
                        {app.status === "draft" && (
                          <Link href={`/applications/${app.id}`}>
                            <Button variant="ghost" size="icon" className="h-7 w-7" data-testid={`edit-app-${app.id}`}>
                              <Pencil className="w-3.5 h-3.5" />
                            </Button>
                          </Link>
                        )}
                        <DeleteCaseButton
                          appId={app.id}
                          markName={app.markName}
                          onDeleted={reload}
                        />
                      </div>
                    </TableCell>
                  </TableRow>
                );
              })}
              {filtered.length === 0 && (
                <TableRow>
                  <TableCell colSpan={8} className="text-center py-8 text-muted-foreground">
                    Заявки не найдены
                  </TableCell>
                </TableRow>
              )}
            </TableBody>
          </Table>
        </div>
      </Card>
    </div>
  );
}

/**
 * Срочность дела: меняется прямо в списке.
 *
 * Это срочность в работе поверенного, а не конвенционный приоритет
 * заявки по статье 1495 — тот определяется датой подачи.
 */
function PrioritySelect({
  appId,
  value,
  onChanged,
}: {
  appId: number;
  value: CasePriority;
  onChanged: () => void;
}) {
  const { toast } = useToast();
  const [isSaving, setIsSaving] = useState(false);

  const change = async (next: string) => {
    setIsSaving(true);
    try {
      await api.put(`/applications/${appId}`, { priority: next });
      onChanged();
    } catch (e) {
      toast({
        title: "Не удалось изменить приоритет",
        description: e instanceof ApiError ? e.message : "Неизвестная ошибка",
        variant: "destructive",
      });
    } finally {
      setIsSaving(false);
    }
  };

  return (
    <Select value={value} onValueChange={(v) => void change(v)} disabled={isSaving}>
      <SelectTrigger
        className={cn(
          "h-7 w-[104px] text-[11px] border-0 focus:ring-0",
          PRIORITY_COLORS[value],
        )}
        data-testid={`priority-${appId}`}
      >
        <SelectValue />
      </SelectTrigger>
      <SelectContent>
        {(Object.keys(PRIORITY_LABELS) as CasePriority[]).map((key) => (
          <SelectItem key={key} value={key} className="text-xs">
            {PRIORITY_LABELS[key]}
          </SelectItem>
        ))}
      </SelectContent>
    </Select>
  );
}

/**
 * Удаление дела.
 *
 * Требует подтверждения: вместе с делом уходят документы, извлечённые
 * поля и результаты анализа. Поданное дело сервер удалить не даст.
 */
function DeleteCaseButton({
  appId,
  markName,
  onDeleted,
}: {
  appId: number;
  markName: string;
  onDeleted: () => void;
}) {
  const { toast } = useToast();
  const [isDeleting, setIsDeleting] = useState(false);

  const remove = async () => {
    const confirmed = window.confirm(
      `Удалить дело «${markName}»?

` +
        "Вместе с ним будут удалены загруженные документы, извлечённые " +
        "поля и результаты анализа. Действие необратимо.",
    );
    if (!confirmed) return;

    setIsDeleting(true);
    try {
      await api.delete(`/applications/${appId}`);
      toast({ title: `Дело «${markName}» удалено` });
      onDeleted();
    } catch (e) {
      toast({
        title: "Не удалось удалить дело",
        description: e instanceof ApiError ? e.message : "Неизвестная ошибка",
        variant: "destructive",
      });
    } finally {
      setIsDeleting(false);
    }
  };

  return (
    <Button
      variant="ghost"
      size="icon"
      className="h-7 w-7 text-muted-foreground hover:text-destructive"
      disabled={isDeleting}
      onClick={() => void remove()}
      data-testid={`delete-app-${appId}`}
      title="Удалить дело"
    >
      <Trash2 className="w-3.5 h-3.5" />
    </Button>
  );
}
