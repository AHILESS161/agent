import { useState } from "react";
import { Link, useLocation } from "wouter";
import { useAuth } from "@/lib/auth";
import { useTheme } from "@/lib/theme";
import { useUnreadCount } from "@/lib/use-unread-count";
import { cn } from "@/lib/utils";
import type { UserRole } from "@shared/schema";
import { ROLE_LABELS } from "@shared/schema";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Avatar, AvatarFallback } from "@/components/ui/avatar";
import { Separator } from "@/components/ui/separator";
import { ScrollArea } from "@/components/ui/scroll-area";
import {
  DropdownMenu, DropdownMenuContent, DropdownMenuItem,
  DropdownMenuSeparator, DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import {
  LayoutDashboard, FileText, Users, Bell, ClipboardList,
  Settings, ChevronLeft, ChevronRight, Moon, Sun, LogOut,
  Shield, PanelLeftClose, PanelLeft, User,
} from "lucide-react";

// SVG Logo
function AppLogo({ collapsed }: { collapsed: boolean }) {
  return (
    <div className="flex items-center gap-2.5 px-3 py-4">
      <svg
        viewBox="0 0 32 32"
        className="w-8 h-8 shrink-0"
        aria-label="ТМ Регистрация"
        fill="none"
      >
        <rect x="2" y="2" width="28" height="28" rx="6" stroke="hsl(174, 83%, 32%)" strokeWidth="2.5" />
        <text x="16" y="22" textAnchor="middle" fill="currentColor" className="text-white" fontSize="14" fontWeight="700" fontFamily="Inter, sans-serif">TM</text>
      </svg>
      {!collapsed && (
        <div className="flex flex-col leading-tight">
          <span className="text-sm font-semibold text-sidebar-foreground">ТМ Регистр</span>
          <span className="text-[10px] text-sidebar-foreground/60">Система регистрации</span>
        </div>
      )}
    </div>
  );
}

interface NavItem {
  label: string;
  href: string;
  icon: typeof LayoutDashboard;
  roles: UserRole[];
  badge?: number;
}

function getNavItems(unreadCount: number): NavItem[] {
  return [
    { label: "Дашборд", href: "/dashboard", icon: LayoutDashboard, roles: ["admin", "lawyer", "manager", "client"] },
    { label: "Заявки", href: "/applications", icon: FileText, roles: ["admin", "lawyer", "manager", "client"] },
    { label: "Клиенты", href: "/clients", icon: Users, roles: ["admin", "lawyer", "manager"] },
    { label: "Уведомления", href: "/notifications", icon: Bell, roles: ["admin", "lawyer", "manager", "client"], badge: unreadCount },
    { label: "Аудит", href: "/audit", icon: ClipboardList, roles: ["admin", "lawyer"] },
    { label: "Администрирование", href: "/admin", icon: Settings, roles: ["admin"] },
  ];
}

function Sidebar({ collapsed, onToggle }: { collapsed: boolean; onToggle: () => void }) {
  const { user } = useAuth();
  const [location] = useLocation();
  const unreadCount = useUnreadCount();
  const navItems = getNavItems(unreadCount).filter(item => user && item.roles.includes(user.role));

  return (
    <aside
      className={cn(
        "fixed left-0 top-0 bottom-0 z-30 flex flex-col border-r border-sidebar-border bg-sidebar transition-all duration-200",
        collapsed ? "w-16" : "w-60"
      )}
      data-testid="sidebar"
    >
      <AppLogo collapsed={collapsed} />
      <Separator className="bg-sidebar-border" />

      <ScrollArea className="flex-1 py-2">
        <nav className="flex flex-col gap-0.5 px-2">
          {navItems.map(item => {
            const isActive = location === item.href || (item.href !== "/dashboard" && location.startsWith(item.href));
            return (
              <Link key={item.href} href={item.href}>
                <div
                  className={cn(
                    "flex items-center gap-3 rounded-md px-3 py-2 text-sm font-medium cursor-pointer transition-colors",
                    isActive
                      ? "bg-sidebar-accent text-sidebar-primary"
                      : "text-sidebar-foreground/70 hover:text-sidebar-foreground hover:bg-sidebar-accent/50"
                  )}
                  data-testid={`nav-${item.href.slice(1)}`}
                >
                  <item.icon className="w-4.5 h-4.5 shrink-0" />
                  {!collapsed && (
                    <>
                      <span className="flex-1">{item.label}</span>
                      {item.badge && item.badge > 0 ? (
                        <Badge variant="destructive" className="h-5 min-w-5 px-1.5 text-[10px] font-semibold">
                          {item.badge}
                        </Badge>
                      ) : null}
                    </>
                  )}
                  {collapsed && item.badge && item.badge > 0 ? (
                    <span className="absolute right-1.5 top-0.5 w-2 h-2 bg-destructive rounded-full" />
                  ) : null}
                </div>
              </Link>
            );
          })}
        </nav>
      </ScrollArea>

      <div className="p-2">
        <Button
          variant="ghost"
          size="sm"
          onClick={onToggle}
          className="w-full justify-center text-sidebar-foreground/60 hover:text-sidebar-foreground hover:bg-sidebar-accent/50"
          data-testid="toggle-sidebar"
        >
          {collapsed ? <PanelLeft className="w-4 h-4" /> : <PanelLeftClose className="w-4 h-4" />}
        </Button>
      </div>
    </aside>
  );
}

function TopBar() {
  const { user, logout } = useAuth();
  const { theme, toggleTheme } = useTheme();
  const [location, setLocation] = useLocation();
  const unreadCount = useUnreadCount();
  const initials = user?.fullName.split(" ").map(s => s[0]).join("").slice(0, 2) || "?";

  return (
    <header className="sticky top-0 z-20 flex items-center justify-between h-14 px-4 border-b bg-background/95 backdrop-blur supports-[backdrop-filter]:bg-background/80" data-testid="topbar">
      <Breadcrumbs />
      <div className="flex items-center gap-2">
        <Button
          variant="ghost"
          size="icon"
          onClick={toggleTheme}
          className="h-8 w-8"
          data-testid="toggle-theme"
        >
          {theme === "dark" ? <Sun className="w-4 h-4" /> : <Moon className="w-4 h-4" />}
        </Button>

        <Button
          variant="ghost"
          size="icon"
          className="h-8 w-8 relative"
          onClick={() => setLocation("/notifications")}
          data-testid="topbar-notifications"
        >
          <Bell className="w-4 h-4" />
          {unreadCount > 0 && (
            <span className="absolute -top-0.5 -right-0.5 w-4 h-4 bg-destructive rounded-full text-[9px] text-white flex items-center justify-center font-bold">
              {unreadCount}
            </span>
          )}
        </Button>

        <DropdownMenu>
          <DropdownMenuTrigger asChild>
            <Button variant="ghost" className="flex items-center gap-2 h-8 px-2" data-testid="user-menu">
              <Avatar className="h-6 w-6">
                <AvatarFallback className="text-[10px] bg-primary text-primary-foreground font-semibold">
                  {initials}
                </AvatarFallback>
              </Avatar>
              <span className="text-sm font-medium hidden sm:inline">{user?.fullName.split(" ").slice(0, 2).join(" ")}</span>
            </Button>
          </DropdownMenuTrigger>
          <DropdownMenuContent align="end" className="w-56">
            <div className="px-2 py-1.5">
              <p className="text-sm font-medium">{user?.fullName}</p>
              <p className="text-xs text-muted-foreground">{user?.email}</p>
              <Badge variant="secondary" className="mt-1 text-[10px]">
                {user ? ROLE_LABELS[user.role] : ""}
              </Badge>
            </div>
            <DropdownMenuSeparator />
            <DropdownMenuItem onClick={logout} data-testid="logout-button">
              <LogOut className="w-4 h-4 mr-2" />
              Выйти
            </DropdownMenuItem>
          </DropdownMenuContent>
        </DropdownMenu>
      </div>
    </header>
  );
}

const breadcrumbMap: Record<string, string> = {
  "/dashboard": "Дашборд",
  "/applications": "Заявки",
  "/applications/new": "Новая заявка",
  "/clients": "Клиенты",
  "/notifications": "Уведомления",
  "/audit": "Журнал аудита",
  "/admin": "Администрирование",
};

function Breadcrumbs() {
  const [location] = useLocation();
  const parts = location.split("/").filter(Boolean);
  const crumbs: { label: string; href: string }[] = [];

  let path = "";
  for (const part of parts) {
    path += `/${part}`;
    const label = breadcrumbMap[path] || (isNaN(Number(part)) ? part : `#${part}`);
    crumbs.push({ label, href: path });
  }

  return (
    <nav className="flex items-center gap-1.5 text-sm text-muted-foreground" data-testid="breadcrumbs">
      {crumbs.map((crumb, i) => (
        <span key={crumb.href} className="flex items-center gap-1.5">
          {i > 0 && <ChevronRight className="w-3 h-3" />}
          {i === crumbs.length - 1 ? (
            <span className="font-medium text-foreground">{crumb.label}</span>
          ) : (
            <Link href={crumb.href}>
              <span className="hover:text-foreground cursor-pointer">{crumb.label}</span>
            </Link>
          )}
        </span>
      ))}
    </nav>
  );
}

export function AppLayout({ children }: { children: React.ReactNode }) {
  const [collapsed, setCollapsed] = useState(false);

  return (
    <div className="min-h-screen bg-background">
      <Sidebar collapsed={collapsed} onToggle={() => setCollapsed(!collapsed)} />
      <div className={cn("transition-all duration-200", collapsed ? "ml-16" : "ml-60")}>
        <TopBar />
        <main className="p-4 lg:p-6" data-testid="main-content">
          {children}
        </main>
      </div>
    </div>
  );
}
