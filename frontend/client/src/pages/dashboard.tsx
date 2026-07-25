import { useAuth } from "@/lib/auth";
import { Link } from "wouter";
import {
  mockApplications, mockUsers, mockClients, mockNotifications,
  mockAuditLogs, getApplicationsByAssignee, getNotifications,
  getApplicationsByClientId,
} from "@/lib/mock-data";
import {
  STATUS_LABELS, STATUS_COLORS, RISK_LABELS, RISK_COLORS, ROLE_LABELS,
  type ApplicationStatus,
} from "@shared/schema";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  FileText, Users, Bell, AlertTriangle, CheckCircle,
  Clock, TrendingUp, ShieldCheck, Activity, ArrowRight,
  BarChart3, Folder, UserCheck,
} from "lucide-react";
import { cn } from "@/lib/utils";

function KpiCard({ title, value, icon: Icon, description, color }: {
  title: string; value: string | number; icon: typeof FileText; description?: string; color?: string;
}) {
  return (
    <Card className="border border-card-border">
      <CardContent className="p-4">
        <div className="flex items-start justify-between">
          <div>
            <p className="text-xs font-medium text-muted-foreground">{title}</p>
            <p className="text-2xl font-bold mt-1" data-testid={`kpi-${title}`}>{value}</p>
            {description && <p className="text-xs text-muted-foreground mt-1">{description}</p>}
          </div>
          <div className={cn("p-2 rounded-lg", color || "bg-primary/10")}>
            <Icon className={cn("w-4.5 h-4.5", color ? "text-inherit" : "text-primary")} />
          </div>
        </div>
      </CardContent>
    </Card>
  );
}

function StatusFunnel() {
  const statusGroups: { label: string; statuses: ApplicationStatus[]; color: string }[] = [
    { label: "Черновик / Сбор данных", statuses: ["draft", "info_requested"], color: "bg-slate-400" },
    { label: "Проверка / Анализ", statuses: ["info_received", "legal_review_pending", "legal_review_in_progress"], color: "bg-blue-500" },
    { label: "Классы / Конфликты", statuses: ["classification_review", "conflict_search_in_progress"], color: "bg-violet-500" },
    { label: "Рекомендации / Документы", statuses: ["memo_approved", "document_generation", "document_approved"], color: "bg-amber-500" },
    { label: "Подача / Мониторинг", statuses: ["submitted"], color: "bg-teal-500" },
    { label: "Завершена / Архив", statuses: ["closed"], color: "bg-green-500" },
  ];

  return (
    <Card className="border border-card-border">
      <CardHeader className="pb-3">
        <CardTitle className="text-sm font-semibold flex items-center gap-2">
          <BarChart3 className="w-4 h-4 text-primary" />
          Воронка заявок
        </CardTitle>
      </CardHeader>
      <CardContent className="space-y-2">
        {statusGroups.map(g => {
          const count = mockApplications.filter(a => g.statuses.includes(a.status)).length;
          const pct = mockApplications.length ? Math.round((count / mockApplications.length) * 100) : 0;
          return (
            <div key={g.label} className="flex items-center gap-3">
              <div className="w-32 text-xs text-muted-foreground truncate">{g.label}</div>
              <div className="flex-1 h-5 bg-muted rounded-full overflow-hidden">
                <div className={cn("h-full rounded-full transition-all", g.color)} style={{ width: `${Math.max(pct, 5)}%` }} />
              </div>
              <span className="text-xs font-mono font-medium w-6 text-right">{count}</span>
            </div>
          );
        })}
      </CardContent>
    </Card>
  );
}

function RecentApplicationsList({ apps, showAssignee }: { apps: typeof mockApplications; showAssignee?: boolean }) {
  return (
    <div className="space-y-2">
      {apps.slice(0, 5).map(app => (
        <Link key={app.id} href={`/applications/${app.id}`}>
          <div className="flex items-center justify-between p-3 rounded-lg border border-card-border hover:bg-accent/50 cursor-pointer transition-colors" data-testid={`app-row-${app.id}`}>
            <div className="flex-1 min-w-0">
              <div className="flex items-center gap-2">
                <span className="text-xs font-mono text-muted-foreground">#{app.id}</span>
                <span className="text-sm font-medium truncate">{app.markName}</span>
              </div>
              {showAssignee && app.assigneeId && (
                <p className="text-xs text-muted-foreground mt-0.5">
                  {mockUsers.find(u => u.id === app.assigneeId)?.fullName}
                </p>
              )}
            </div>
            <Badge className={cn("text-[10px] ml-2 shrink-0", STATUS_COLORS[app.status])}>
              {STATUS_LABELS[app.status]}
            </Badge>
          </div>
        </Link>
      ))}
    </div>
  );
}

function NotificationsList({ userId }: { userId: number }) {
  const notifs = getNotifications(userId).slice(0, 5);
  return (
    <div className="space-y-2">
      {notifs.map(n => (
        <Link key={n.id} href={`/applications/${n.applicationId}`}>
          <div className={cn(
            "p-3 rounded-lg border border-card-border cursor-pointer transition-colors hover:bg-accent/50",
            !n.isRead && "bg-primary/5 border-primary/20"
          )}>
            <div className="flex items-start justify-between">
              <p className="text-sm font-medium">{n.title}</p>
              {!n.isRead && <span className="w-2 h-2 bg-primary rounded-full mt-1 shrink-0" />}
            </div>
            <p className="text-xs text-muted-foreground mt-0.5">{n.message}</p>
            <p className="text-[10px] text-muted-foreground/60 mt-1">
              {new Date(n.createdAt).toLocaleDateString("ru-RU", { day: "numeric", month: "short", hour: "2-digit", minute: "2-digit" })}
            </p>
          </div>
        </Link>
      ))}
    </div>
  );
}

// ========== ROLE DASHBOARDS ==========

function LawyerDashboard({ userId }: { userId: number }) {
  const assigned = getApplicationsByAssignee(userId);
  const pending = assigned.filter(a => ["legal_review_in_progress", "memo_approved", "document_approved"].includes(a.status));
  const highRisk = assigned.filter(a => ["conflict_search_in_progress", "submitted"].includes(a.status));

  return (
    <div className="space-y-6">
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
        <KpiCard title="Активные заявки" value={assigned.filter(a => !["closed", "rejected", "closed"].includes(a.status)).length} icon={FileText} />
        <KpiCard title="Ожидают рассмотрения" value={pending.length} icon={Clock} description="Требуется ваше решение" color="bg-amber-100 dark:bg-amber-900/30" />
        <KpiCard title="Высокий риск" value={highRisk.length} icon={AlertTriangle} color="bg-red-100 dark:bg-red-900/30" />
        <KpiCard title="Завершено" value={assigned.filter(a => a.status === "closed").length} icon={CheckCircle} color="bg-green-100 dark:bg-green-900/30" />
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        <Card className="border border-card-border">
          <CardHeader className="pb-3">
            <div className="flex items-center justify-between">
              <CardTitle className="text-sm font-semibold">Ожидают рассмотрения</CardTitle>
              <Link href="/applications">
                <Button variant="ghost" size="sm" className="text-xs"><ArrowRight className="w-3 h-3 ml-1" />Все заявки</Button>
              </Link>
            </div>
          </CardHeader>
          <CardContent>
            <RecentApplicationsList apps={pending.length ? pending : assigned} />
          </CardContent>
        </Card>

        <Card className="border border-card-border">
          <CardHeader className="pb-3">
            <CardTitle className="text-sm font-semibold flex items-center gap-2">
              <Bell className="w-4 h-4 text-primary" /> Уведомления
            </CardTitle>
          </CardHeader>
          <CardContent>
            <NotificationsList userId={userId} />
          </CardContent>
        </Card>
      </div>
    </div>
  );
}

function ManagerDashboard() {
  const total = mockApplications.length;
  const active = mockApplications.filter(a => !["closed", "rejected", "closed", "draft"].includes(a.status));
  const awaitingData = mockApplications.filter(a => a.status === "info_requested");

  return (
    <div className="space-y-6">
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
        <KpiCard title="Всего заявок" value={total} icon={Folder} />
        <KpiCard title="В работе" value={active.length} icon={Activity} />
        <KpiCard title="Ожидают данных" value={awaitingData.length} icon={Clock} color="bg-amber-100 dark:bg-amber-900/30" />
        <KpiCard title="Клиентов" value={mockClients.length} icon={Users} color="bg-blue-100 dark:bg-blue-900/30" />
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        <StatusFunnel />
        <Card className="border border-card-border">
          <CardHeader className="pb-3">
            <div className="flex items-center justify-between">
              <CardTitle className="text-sm font-semibold">Последние заявки</CardTitle>
              <Link href="/applications/new">
                <Button size="sm" className="text-xs" data-testid="new-app-btn">Новая заявка</Button>
              </Link>
            </div>
          </CardHeader>
          <CardContent>
            <RecentApplicationsList apps={[...mockApplications].sort((a, b) => new Date(b.updatedAt).getTime() - new Date(a.updatedAt).getTime())} showAssignee />
          </CardContent>
        </Card>
      </div>
    </div>
  );
}

function ClientDashboard({ userId }: { userId: number }) {
  // Client's applications — linked by clientId. For demo, client user 4 maps to client 4.
  const clientId = userId;
  const myApps = getApplicationsByClientId(clientId);
  const actionRequired = myApps.filter(a => ["info_requested", "info_requested"].includes(a.status));

  return (
    <div className="space-y-6">
      <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
        <KpiCard title="Мои заявки" value={myApps.length} icon={FileText} />
        <KpiCard title="Требуют действий" value={actionRequired.length} icon={AlertTriangle} color="bg-amber-100 dark:bg-amber-900/30" />
        <KpiCard title="Завершено" value={myApps.filter(a => a.status === "closed").length} icon={CheckCircle} color="bg-green-100 dark:bg-green-900/30" />
      </div>

      <Card className="border border-card-border">
        <CardHeader className="pb-3">
          <CardTitle className="text-sm font-semibold">Мои заявки</CardTitle>
        </CardHeader>
        <CardContent>
          <RecentApplicationsList apps={myApps} />
          {myApps.length === 0 && (
            <p className="text-sm text-muted-foreground text-center py-8">У вас пока нет заявок</p>
          )}
        </CardContent>
      </Card>

      <Card className="border border-card-border">
        <CardHeader className="pb-3">
          <CardTitle className="text-sm font-semibold flex items-center gap-2">
            <Bell className="w-4 h-4 text-primary" /> Уведомления
          </CardTitle>
        </CardHeader>
        <CardContent>
          <NotificationsList userId={userId} />
        </CardContent>
      </Card>
    </div>
  );
}

function AdminDashboard() {
  const recentAudit = mockAuditLogs.sort((a, b) => new Date(b.createdAt).getTime() - new Date(a.createdAt).getTime()).slice(0, 6);

  return (
    <div className="space-y-6">
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
        <KpiCard title="Пользователей" value={mockUsers.length} icon={UserCheck} />
        <KpiCard title="Заявок" value={mockApplications.length} icon={FileText} />
        <KpiCard title="Клиентов" value={mockClients.length} icon={Users} color="bg-blue-100 dark:bg-blue-900/30" />
        <KpiCard title="Активных юристов" value={mockUsers.filter(u => u.role === "lawyer" && u.isActive).length} icon={ShieldCheck} color="bg-teal-100 dark:bg-teal-900/30" />
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        <StatusFunnel />
        <Card className="border border-card-border">
          <CardHeader className="pb-3">
            <CardTitle className="text-sm font-semibold flex items-center gap-2">
              <Activity className="w-4 h-4 text-primary" /> Последние события
            </CardTitle>
          </CardHeader>
          <CardContent>
            <div className="space-y-2">
              {recentAudit.map(log => (
                <div key={log.id} className="flex items-start gap-3 p-2 rounded-md hover:bg-accent/50">
                  <div className="w-1.5 h-1.5 bg-primary rounded-full mt-1.5 shrink-0" />
                  <div className="flex-1 min-w-0">
                    <p className="text-sm">{log.action}</p>
                    <p className="text-[10px] text-muted-foreground">
                      {mockUsers.find(u => u.id === log.userId)?.fullName} · {new Date(log.createdAt).toLocaleDateString("ru-RU", { day: "numeric", month: "short", hour: "2-digit", minute: "2-digit" })}
                    </p>
                  </div>
                </div>
              ))}
            </div>
          </CardContent>
        </Card>
      </div>
    </div>
  );
}

export default function DashboardPage() {
  const { user } = useAuth();
  if (!user) return null;

  const greetingTime = new Date().getHours();
  const greeting = greetingTime < 12 ? "Доброе утро" : greetingTime < 18 ? "Добрый день" : "Добрый вечер";

  return (
    <div className="space-y-6" data-testid="dashboard-page">
      <div>
        <h1 className="text-xl font-bold">{greeting}, {user.fullName.split(" ")[0]}</h1>
        <p className="text-sm text-muted-foreground">{ROLE_LABELS[user.role]} · {new Date().toLocaleDateString("ru-RU", { weekday: "long", day: "numeric", month: "long", year: "numeric" })}</p>
      </div>

      {user.role === "lawyer" && <LawyerDashboard userId={user.id} />}
      {user.role === "manager" && <ManagerDashboard />}
      {user.role === "client" && <ClientDashboard userId={user.id} />}
      {user.role === "admin" && <AdminDashboard />}
    </div>
  );
}
