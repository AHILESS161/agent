import { useState } from "react";
import { mockUsers, mockApplications, mockClients, mockAuditLogs } from "@/lib/mock-data";
import { ROLE_LABELS, type UserRole } from "@shared/schema";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import {
  Select, SelectContent, SelectItem, SelectTrigger, SelectValue,
} from "@/components/ui/select";
import {
  Users, Settings, Activity, Database, Server,
  UserPlus, Shield, FileText, CheckCircle, XCircle,
} from "lucide-react";
import { cn } from "@/lib/utils";
import { useToast } from "@/hooks/use-toast";

function SystemStats() {
  const stats = [
    { label: "Пользователей", value: mockUsers.length, icon: Users },
    { label: "Заявок", value: mockApplications.length, icon: FileText },
    { label: "Клиентов", value: mockClients.length, icon: Database },
    { label: "Событий аудита", value: mockAuditLogs.length, icon: Activity },
  ];

  return (
    <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
      {stats.map(s => (
        <Card key={s.label} className="border border-card-border">
          <CardContent className="p-4 flex items-center gap-3">
            <div className="p-2 rounded-lg bg-primary/10">
              <s.icon className="w-4.5 h-4.5 text-primary" />
            </div>
            <div>
              <p className="text-xs text-muted-foreground">{s.label}</p>
              <p className="text-xl font-bold">{s.value}</p>
            </div>
          </CardContent>
        </Card>
      ))}
    </div>
  );
}

function UsersManagement() {
  const { toast } = useToast();

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <p className="text-sm text-muted-foreground">{mockUsers.length} пользователей</p>
        <Button size="sm" data-testid="button-add-user">
          <UserPlus className="w-3.5 h-3.5 mr-1.5" /> Добавить
        </Button>
      </div>

      <Card className="border border-card-border overflow-hidden">
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead>Пользователь</TableHead>
              <TableHead>Email</TableHead>
              <TableHead>Роль</TableHead>
              <TableHead className="w-20">Статус</TableHead>
              <TableHead className="w-32">Действие</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {mockUsers.map(u => (
              <TableRow key={u.id} data-testid={`user-row-${u.id}`}>
                <TableCell className="text-sm font-medium">{u.fullName}</TableCell>
                <TableCell className="text-sm text-muted-foreground font-mono">{u.email}</TableCell>
                <TableCell>
                  <Badge variant="secondary" className="text-[10px]">
                    <Shield className="w-3 h-3 mr-1" /> {ROLE_LABELS[u.role]}
                  </Badge>
                </TableCell>
                <TableCell>
                  {u.isActive ? (
                    <Badge className="bg-green-100 text-green-800 dark:bg-green-900/30 dark:text-green-400 text-[10px]">
                      <CheckCircle className="w-3 h-3 mr-1" /> Активен
                    </Badge>
                  ) : (
                    <Badge variant="secondary" className="text-[10px]">
                      <XCircle className="w-3 h-3 mr-1" /> Отключён
                    </Badge>
                  )}
                </TableCell>
                <TableCell>
                  <Select defaultValue={u.role}>
                    <SelectTrigger className="h-7 text-xs w-28" data-testid={`role-select-${u.id}`}>
                      <SelectValue />
                    </SelectTrigger>
                    <SelectContent>
                      {(Object.keys(ROLE_LABELS) as UserRole[]).map(r => (
                        <SelectItem key={r} value={r}>{ROLE_LABELS[r]}</SelectItem>
                      ))}
                    </SelectContent>
                  </Select>
                </TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>
      </Card>
    </div>
  );
}

function BackgroundJobs() {
  const jobs = [
    { name: "legal_precheck", label: "Правовой пречек", status: "idle", lastRun: "2026-03-29 12:00" },
    { name: "conflict_search", label: "Поиск конфликтов", status: "running", lastRun: "2026-03-29 13:45" },
    { name: "doc_generation", label: "Генерация документов", status: "idle", lastRun: "2026-03-29 11:30" },
    { name: "class_suggestion", label: "Предложение классов", status: "idle", lastRun: "2026-03-29 10:00" },
  ];

  const statusLabels: Record<string, { label: string; color: string }> = {
    idle: { label: "Ожидание", color: "bg-slate-100 text-slate-700 dark:bg-slate-800 dark:text-slate-300" },
    running: { label: "Выполняется", color: "bg-green-100 text-green-800 dark:bg-green-900/30 dark:text-green-400" },
    error: { label: "Ошибка", color: "bg-red-100 text-red-800 dark:bg-red-900/30 dark:text-red-400" },
  };

  return (
    <Card className="border border-card-border overflow-hidden">
      <Table>
        <TableHeader>
          <TableRow>
            <TableHead>Задача</TableHead>
            <TableHead>Статус</TableHead>
            <TableHead>Последний запуск</TableHead>
          </TableRow>
        </TableHeader>
        <TableBody>
          {jobs.map(j => (
            <TableRow key={j.name} data-testid={`job-row-${j.name}`}>
              <TableCell className="text-sm font-medium">{j.label}</TableCell>
              <TableCell>
                <Badge className={cn("text-[10px]", statusLabels[j.status].color)}>
                  {statusLabels[j.status].label}
                </Badge>
              </TableCell>
              <TableCell className="text-xs text-muted-foreground font-mono">{j.lastRun}</TableCell>
            </TableRow>
          ))}
        </TableBody>
      </Table>
    </Card>
  );
}

function PromptVersions() {
  const prompts = [
    { name: "legal_precheck_v2", version: "2.1.0", updated: "2026-03-15", status: "active" },
    { name: "class_suggestion_v3", version: "3.0.1", updated: "2026-03-20", status: "active" },
    { name: "conflict_analysis_v1", version: "1.2.0", updated: "2026-03-10", status: "active" },
    { name: "doc_generation_v2", version: "2.0.0", updated: "2026-03-01", status: "draft" },
    { name: "recommendation_v1", version: "1.0.0", updated: "2026-02-28", status: "active" },
  ];

  return (
    <Card className="border border-card-border overflow-hidden">
      <Table>
        <TableHeader>
          <TableRow>
            <TableHead>Промпт</TableHead>
            <TableHead>Версия</TableHead>
            <TableHead>Обновлён</TableHead>
            <TableHead>Статус</TableHead>
          </TableRow>
        </TableHeader>
        <TableBody>
          {prompts.map(p => (
            <TableRow key={p.name}>
              <TableCell className="text-sm font-mono">{p.name}</TableCell>
              <TableCell className="text-sm font-mono text-muted-foreground">{p.version}</TableCell>
              <TableCell className="text-xs text-muted-foreground">{p.updated}</TableCell>
              <TableCell>
                <Badge variant={p.status === "active" ? "default" : "secondary"} className="text-[10px]">
                  {p.status === "active" ? "Активен" : "Черновик"}
                </Badge>
              </TableCell>
            </TableRow>
          ))}
        </TableBody>
      </Table>
    </Card>
  );
}

export default function AdminPage() {
  return (
    <div className="space-y-6" data-testid="admin-page">
      <h1 className="text-xl font-bold">Администрирование</h1>

      <SystemStats />

      <Tabs defaultValue="users">
        <TabsList>
          <TabsTrigger value="users" className="text-xs" data-testid="admin-tab-users">
            <Users className="w-3.5 h-3.5 mr-1.5" /> Пользователи
          </TabsTrigger>
          <TabsTrigger value="jobs" className="text-xs" data-testid="admin-tab-jobs">
            <Server className="w-3.5 h-3.5 mr-1.5" /> Задачи
          </TabsTrigger>
          <TabsTrigger value="prompts" className="text-xs" data-testid="admin-tab-prompts">
            <Settings className="w-3.5 h-3.5 mr-1.5" /> Промпты
          </TabsTrigger>
        </TabsList>
        <TabsContent value="users" className="mt-4">
          <UsersManagement />
        </TabsContent>
        <TabsContent value="jobs" className="mt-4">
          <BackgroundJobs />
        </TabsContent>
        <TabsContent value="prompts" className="mt-4">
          <PromptVersions />
        </TabsContent>
      </Tabs>
    </div>
  );
}
