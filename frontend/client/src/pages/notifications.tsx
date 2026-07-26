import { Link } from "wouter";
import { Card, CardContent } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { useToast } from "@/hooks/use-toast";
import { AsyncSection } from "@/components/async-states";
import { api, ApiError } from "@/lib/api";
import { useApi, type NotificationsDto } from "@/lib/use-api";
import { cn } from "@/lib/utils";
import { Bell, Check, ExternalLink } from "lucide-react";

const TYPE_STYLES: Record<string, string> = {
  info: "bg-blue-500/15 text-blue-700 dark:text-blue-400",
  warning: "bg-amber-500/15 text-amber-700 dark:text-amber-500",
  action_required: "bg-red-500/15 text-red-700 dark:text-red-400",
  status_change: "bg-slate-500/15 text-slate-700 dark:text-slate-300",
};

const TYPE_LABELS: Record<string, string> = {
  info: "Информация",
  warning: "Предупреждение",
  action_required: "Требуется действие",
  status_change: "Изменение статуса",
};

export default function NotificationsPage() {
  const { toast } = useToast();
  const state = useApi<NotificationsDto>("/notifications?page=1&page_size=100");

  const markAllRead = async () => {
    try {
      await api.post("/notifications/mark-read", {});
      state.reload();
    } catch (e) {
      toast({
        title: "Не удалось отметить прочитанными",
        description: e instanceof ApiError ? e.message : "Неизвестная ошибка",
        variant: "destructive",
      });
    }
  };

  const markRead = async (id: number) => {
    try {
      await api.put(`/notifications/${id}/read`);
      state.reload();
    } catch (e) {
      toast({
        title: "Не удалось отметить прочитанным",
        description: e instanceof ApiError ? e.message : "Неизвестная ошибка",
        variant: "destructive",
      });
    }
  };

  return (
    <div className="space-y-4 max-w-2xl" data-testid="notifications-page">
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-3">
          <h1 className="text-xl font-bold">Уведомления</h1>
          {(state.data?.unread_count ?? 0) > 0 && (
            <Badge variant="destructive" className="text-[10px]">
              {state.data?.unread_count} новых
            </Badge>
          )}
        </div>
        {(state.data?.unread_count ?? 0) > 0 && (
          <Button
            variant="outline"
            size="sm"
            onClick={() => void markAllRead()}
            data-testid="mark-all-read"
          >
            <Check className="w-3.5 h-3.5 mr-1.5" />
            Прочитать все
          </Button>
        )}
      </div>

      <AsyncSection
        state={state}
        loadingLabel="Загрузка уведомлений…"
        emptyTitle="Уведомлений нет"
      >
        {(data) =>
          data.items.length === 0 ? (
            <Card className="border-dashed">
              <CardContent className="flex flex-col items-center justify-center py-10 text-center">
                <Bell className="w-8 h-8 text-muted-foreground mb-3" />
                <p className="text-sm font-medium">Уведомлений пока нет</p>
                <p className="text-xs text-muted-foreground mt-1">
                  Здесь появятся события по вашим делам.
                </p>
              </CardContent>
            </Card>
          ) : (
            <div className="space-y-2">
              {data.items.map((item) => (
                <Card
                  key={item.id}
                  className={cn(!item.is_read && "border-primary/40")}
                  data-testid={`notification-${item.id}`}
                >
                  <CardContent className="p-3">
                    <div className="flex items-start justify-between gap-3">
                      <div className="min-w-0 flex-1">
                        <div className="flex flex-wrap items-center gap-2">
                          <span className="text-sm font-medium">{item.title}</span>
                          <Badge
                            className={cn("text-[10px]", TYPE_STYLES[item.type])}
                          >
                            {TYPE_LABELS[item.type] ?? item.type}
                          </Badge>
                          {!item.is_read && (
                            <span className="h-1.5 w-1.5 rounded-full bg-primary" />
                          )}
                        </div>
                        <p className="text-xs text-muted-foreground mt-1">
                          {item.message}
                        </p>
                        <p className="text-[10px] text-muted-foreground mt-1">
                          {new Date(item.created_at).toLocaleString("ru-RU")}
                        </p>
                      </div>
                      <div className="flex items-center gap-1 shrink-0">
                        {item.application_id && (
                          <Link href={`/applications/${item.application_id}`}>
                            <Button variant="ghost" size="icon" className="h-7 w-7">
                              <ExternalLink className="w-3.5 h-3.5" />
                            </Button>
                          </Link>
                        )}
                        {!item.is_read && (
                          <Button
                            variant="ghost"
                            size="icon"
                            className="h-7 w-7"
                            onClick={() => void markRead(item.id)}
                            data-testid={`mark-read-${item.id}`}
                          >
                            <Check className="w-3.5 h-3.5" />
                          </Button>
                        )}
                      </div>
                    </div>
                  </CardContent>
                </Card>
              ))}
            </div>
          )
        }
      </AsyncSection>
    </div>
  );
}
