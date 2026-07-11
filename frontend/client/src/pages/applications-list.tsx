import { useState, useMemo } from "react";
import { Link } from "wouter";
import { useAuth } from "@/lib/auth";
import { mockApplications, mockClients, mockUsers, getApplicationsByClientId, getApplicationsByAssignee } from "@/lib/mock-data";
import { STATUS_LABELS, STATUS_COLORS, MARK_TYPE_LABELS, type ApplicationStatus } from "@shared/schema";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { Plus, Search, Filter, Eye, Pencil } from "lucide-react";
import { cn } from "@/lib/utils";

export default function ApplicationsListPage() {
  const { user } = useAuth();
  const [search, setSearch] = useState("");
  const [statusFilter, setStatusFilter] = useState<string>("all");

  const baseApps = useMemo(() => {
    if (!user) return [];
    if (user.role === "client") return getApplicationsByClientId(user.id);
    if (user.role === "lawyer") return getApplicationsByAssignee(user.id);
    return mockApplications;
  }, [user]);

  const filtered = useMemo(() => {
    return baseApps.filter(app => {
      if (statusFilter !== "all" && app.status !== statusFilter) return false;
      if (search) {
        const q = search.toLowerCase();
        const client = mockClients.find(c => c.id === app.clientId);
        return (
          app.markName.toLowerCase().includes(q) ||
          app.id.toString().includes(q) ||
          client?.shortName.toLowerCase().includes(q)
        );
      }
      return true;
    });
  }, [baseApps, search, statusFilter]);

  const statusOptions: ApplicationStatus[] = [...new Set(baseApps.map(a => a.status))];

  return (
    <div className="space-y-4" data-testid="applications-list-page">
      <div className="flex items-center justify-between">
        <h1 className="text-xl font-bold">Заявки</h1>
        {user?.role !== "client" && (
          <Link href="/applications/new">
            <Button size="sm" data-testid="button-new-application">
              <Plus className="w-4 h-4 mr-1.5" />
              Новая заявка
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
                <TableHead className="hidden md:table-cell">Исполнитель</TableHead>
                <TableHead className="hidden lg:table-cell">Обновлено</TableHead>
                <TableHead className="w-20"></TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {filtered.map(app => {
                const client = mockClients.find(c => c.id === app.clientId);
                const assignee = app.assigneeId ? mockUsers.find(u => u.id === app.assigneeId) : null;
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
                    <TableCell className="hidden md:table-cell text-sm text-muted-foreground">
                      {assignee ? assignee.fullName.split(" ").slice(0, 2).join(" ") : "—"}
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
