import { useState } from "react";
import { Link } from "wouter";
import { useAuth } from "@/lib/auth";
import { getNotifications } from "@/lib/mock-data";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Bell, Check, ExternalLink } from "lucide-react";
import { cn } from "@/lib/utils";

export default function NotificationsPage() {
  const { user } = useAuth();
  const [readIds, setReadIds] = useState<Set<number>>(new Set());
  const notifs = user ? getNotifications(user.id) : [];

  const isRead = (n: typeof notifs[0]) => n.isRead || readIds.has(n.id);
  const unreadCount = notifs.filter(n => !isRead(n)).length;

  const markAllRead = () => {
    setReadIds(new Set(notifs.map(n => n.id)));
  };

  const markRead = (id: number) => {
    setReadIds(prev => new Set([...prev, id]));
  };

  // Group by date
  const grouped = notifs.reduce((acc, n) => {
    const d = new Date(n.createdAt).toLocaleDateString("ru-RU", { day: "numeric", month: "long", year: "numeric" });
    if (!acc[d]) acc[d] = [];
    acc[d].push(n);
    return acc;
  }, {} as Record<string, typeof notifs>);

  return (
    <div className="space-y-4 max-w-2xl" data-testid="notifications-page">
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-3">
          <h1 className="text-xl font-bold">Уведомления</h1>
          {unreadCount > 0 && (
            <Badge variant="destructive" className="text-[10px]">{unreadCount} новых</Badge>
          )}
        </div>
        {unreadCount > 0 && (
          <Button variant="outline" size="sm" onClick={markAllRead} data-testid="mark-all-read">
            <Check className="w-3.5 h-3.5 mr-1.5" /> Прочитать все
          </Button>
        )}
      </div>

      {notifs.length === 0 ? (
        <Card className="border border-card-border">
          <CardContent className="p-8 text-center text-muted-foreground">
            <Bell className="w-8 h-8 mx-auto mb-2 opacity-50" />
            <p className="text-sm">Нет уведомлений</p>
          </CardContent>
        </Card>
      ) : (
        Object.entries(grouped).map(([date, items]) => (
          <div key={date}>
            <p className="text-xs font-semibold text-muted-foreground mb-2">{date}</p>
            <div className="space-y-2">
              {items.map(n => {
                const read = isRead(n);
                return (
                  <Card
                    key={n.id}
                    className={cn(
                      "border border-card-border cursor-pointer transition-colors hover:bg-accent/50",
                      !read && "bg-primary/5 border-primary/20"
                    )}
                    onClick={() => markRead(n.id)}
                    data-testid={`notification-${n.id}`}
                  >
                    <CardContent className="p-3">
                      <div className="flex items-start justify-between gap-2">
                        <div className="flex-1 min-w-0">
                          <div className="flex items-center gap-2">
                            {!read && <span className="w-2 h-2 bg-primary rounded-full shrink-0" />}
                            <p className="text-sm font-medium">{n.title}</p>
                          </div>
                          <p className="text-xs text-muted-foreground mt-0.5">{n.message}</p>
                          <p className="text-[10px] text-muted-foreground/60 mt-1">
                            {new Date(n.createdAt).toLocaleTimeString("ru-RU", { hour: "2-digit", minute: "2-digit" })}
                          </p>
                        </div>
                        <Link href={`/applications/${n.applicationId}`}>
                          <Button variant="ghost" size="icon" className="h-7 w-7 shrink-0" data-testid={`goto-app-${n.applicationId}`}>
                            <ExternalLink className="w-3.5 h-3.5" />
                          </Button>
                        </Link>
                      </div>
                    </CardContent>
                  </Card>
                );
              })}
            </div>
          </div>
        ))
      )}
    </div>
  );
}
