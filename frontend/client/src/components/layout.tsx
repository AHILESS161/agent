import { useState } from "react";
import { Link, useLocation } from "wouter";
import { useAuth } from "@/lib/auth";
import { useTheme } from "@/lib/theme";
import { useUnreadCount } from "@/lib/use-unread-count";
import { cn } from "@/lib/utils";
import type { UserRole } from "@shared/schema";
import { ROLE_LABELS } from "@shared/schema";
import { Button } from "@/components/ui/button";
import { Avatar, AvatarFallback } from "@/components/ui/avatar";
import { BrandWordmark } from "@/components/brand-wordmark";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuLabel,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import {
  LayoutGrid,
  Tags,
  Users,
  Bell,
  Plus,
  Search,
  LogOut,
  User,
  ShieldCheck,
  Settings,
  Moon,
  Sun,
  Menu,
  X,
} from "lucide-react";

interface NavItem {
  label: string;
  href: string;
  icon: typeof LayoutGrid;
  roles: UserRole[];
}

const NAV_ITEMS: NavItem[] = [
  { label: "Обзор", href: "/dashboard", icon: LayoutGrid, roles: ["admin", "lawyer", "manager", "client"] },
  { label: "Заявители", href: "/clients", icon: Users, roles: ["admin", "lawyer", "manager"] },
  { label: "Товарные знаки", href: "/applications", icon: Tags, roles: ["admin", "lawyer", "manager", "client"] },
];

function Wordmark() {
  return (
    <Link href="/dashboard">
      <div className="cursor-pointer px-7 py-9 text-[2rem] leading-none text-white">
        <BrandWordmark accentEnd />
      </div>
    </Link>
  );
}

function Navigation({ onNavigate }: { onNavigate?: () => void }) {
  const { user } = useAuth();
  const [location] = useLocation();
  const items = NAV_ITEMS.filter((item) => user && item.roles.includes(user.role));

  return (
    <nav className="space-y-1 px-3">
      {items.map((item) => {
        const active = location === item.href || (item.href !== "/dashboard" && location.startsWith(item.href));
        return (
          <Link key={item.href} href={item.href} onClick={onNavigate}>
            <div
              className={cn(
                "group relative flex min-h-[48px] cursor-pointer items-center gap-3 rounded-md px-4 py-3 text-[14px] font-medium transition-colors",
                active
                  ? "bg-[#242527] text-[#ffffff]"
                  : "text-[#a9aaaf] hover:bg-[#17181a] hover:text-white",
              )}
              data-testid={`nav-${item.href.slice(1)}`}
            >
              {active && <span className="absolute inset-y-2 left-0 w-[3px] rounded-full bg-primary" />}
              <item.icon className="h-5 w-5" strokeWidth={1.75} />
              <span>{item.label}</span>
            </div>
          </Link>
        );
      })}
    </nav>
  );
}

function UserSummary() {
  const { user, logout } = useAuth();
  const initials = user?.fullName.split(" ").map((part) => part[0]).join("").slice(0, 2) || "?";

  return (
    <div className="shrink-0 border-t border-white/10 px-5 py-5">
      <Link href="/profile">
        <div className="flex cursor-pointer items-center gap-3 text-white/80 hover:text-white">
          <Avatar className="h-9 w-9 border border-white/30">
            <AvatarFallback className="bg-transparent text-xs text-white">{initials}</AvatarFallback>
          </Avatar>
          <div className="min-w-0 flex-1">
            <p className="truncate text-sm font-medium">{user?.fullName}</p>
            <p className="truncate text-[11px] text-white/50">{user ? ROLE_LABELS[user.role] : ""}</p>
          </div>
        </div>
      </Link>
      <button
        type="button"
        onClick={logout}
        className="mt-4 flex items-center gap-2 text-xs text-white/60 transition-colors hover:text-white"
        data-testid="logout-button"
      >
        <LogOut className="h-4 w-4" />
        Выйти
      </button>
    </div>
  );
}

function Sidebar() {
  return (
    <aside className="fixed inset-y-0 left-0 z-30 hidden w-[15rem] flex-col bg-[#08090b] lg:flex" data-testid="sidebar">
      <Wordmark />
      <Navigation />
      <div className="min-h-5 flex-1" />
      <UserSummary />
    </aside>
  );
}

function TopBar() {
  const { user, logout } = useAuth();
  const { theme, toggleTheme } = useTheme();
  const unreadCount = useUnreadCount();
  const [, setLocation] = useLocation();
  const [query, setQuery] = useState("");
  const [mobileMenu, setMobileMenu] = useState(false);
  const initials = user?.fullName.split(" ").map((part) => part[0]).join("").slice(0, 2) || "?";
  const canCreate = user?.role !== "client";

  const search = (event: React.FormEvent) => {
    event.preventDefault();
    const value = query.trim();
    setLocation(value ? `/applications?search=${encodeURIComponent(value)}` : "/applications");
  };

  return (
    <>
      <header className="sticky top-0 z-20 flex h-[5.5rem] items-center gap-4 border-b border-border/70 bg-background/95 px-5 backdrop-blur lg:px-10" data-testid="topbar">
        <Button variant="ghost" size="icon" className="lg:hidden" onClick={() => setMobileMenu(true)} aria-label="Открыть меню">
          <Menu className="h-5 w-5" />
        </Button>

        <form onSubmit={search} className="relative max-w-[470px] flex-1">
          <Search className="absolute left-4 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground" />
          <input
            value={query}
            onChange={(event) => setQuery(event.target.value)}
            className="h-11 w-full rounded-md border border-border bg-card pl-11 pr-4 text-sm outline-none transition-colors placeholder:text-muted-foreground/70 focus:border-primary"
            placeholder="Заявитель, знак или номер заявки"
            aria-label="Поиск"
          />
        </form>

        <div className="ml-auto flex items-center gap-2 sm:gap-4">
          {canCreate && (
            <Button
              variant="outline"
              className="h-11 border-primary px-4 text-primary shadow-none hover:bg-primary/5 sm:px-6"
              onClick={() => setLocation("/intake")}
              data-testid="button-create-global"
            >
              <Plus className="h-4 w-4" />
              <span className="hidden sm:inline">Создать</span>
            </Button>
          )}
          <Button variant="ghost" size="icon" className="relative" onClick={() => setLocation("/notifications")} data-testid="topbar-notifications">
            <Bell className="h-5 w-5" strokeWidth={1.7} />
            {unreadCount > 0 && <span className="absolute right-1 top-1 h-2 w-2 rounded-full bg-primary" />}
          </Button>

          <DropdownMenu>
            <DropdownMenuTrigger asChild>
              <Button variant="ghost" size="icon" className="rounded-full" data-testid="user-menu">
                <Avatar className="h-10 w-10 border border-border">
                  <AvatarFallback className="bg-transparent text-sm text-foreground">{initials}</AvatarFallback>
                </Avatar>
              </Button>
            </DropdownMenuTrigger>
            <DropdownMenuContent align="end" className="w-60">
              <DropdownMenuLabel>
                <p className="font-medium">{user?.fullName}</p>
                <p className="mt-0.5 text-xs font-normal text-muted-foreground">{user?.email}</p>
              </DropdownMenuLabel>
              <DropdownMenuSeparator />
              <DropdownMenuItem onClick={() => setLocation("/profile")} data-testid="profile-button">
                <User className="mr-2 h-4 w-4" /> Профиль
              </DropdownMenuItem>
              {(user?.role === "admin" || user?.role === "lawyer") && (
                <DropdownMenuItem onClick={() => setLocation("/audit")}>
                  <ShieldCheck className="mr-2 h-4 w-4" /> Журнал действий
                </DropdownMenuItem>
              )}
              {user?.role === "admin" && (
                <DropdownMenuItem onClick={() => setLocation("/admin")}>
                  <Settings className="mr-2 h-4 w-4" /> Настройки системы
                </DropdownMenuItem>
              )}
              <DropdownMenuItem onClick={toggleTheme}>
                {theme === "dark" ? <Sun className="mr-2 h-4 w-4" /> : <Moon className="mr-2 h-4 w-4" />}
                {theme === "dark" ? "Светлая тема" : "Тёмная тема"}
              </DropdownMenuItem>
              <DropdownMenuSeparator />
              <DropdownMenuItem onClick={logout}>
                <LogOut className="mr-2 h-4 w-4" /> Выйти
              </DropdownMenuItem>
            </DropdownMenuContent>
          </DropdownMenu>
        </div>
      </header>

      {mobileMenu && (
        <div className="fixed inset-0 z-50 lg:hidden">
          <button className="absolute inset-0 bg-black/50" onClick={() => setMobileMenu(false)} aria-label="Закрыть меню" />
          <aside className="relative flex h-full w-[280px] flex-col bg-[#08090b] shadow-2xl">
            <div className="flex items-center justify-between pr-4">
              <Wordmark />
              <Button variant="ghost" size="icon" className="text-white hover:bg-white/10" onClick={() => setMobileMenu(false)}>
                <X className="h-5 w-5" />
              </Button>
            </div>
            <Navigation onNavigate={() => setMobileMenu(false)} />
            <div className="flex-1" />
            <UserSummary />
          </aside>
        </div>
      )}
    </>
  );
}

export function AppLayout({ children }: { children: React.ReactNode }) {
  return (
    <div className="min-h-screen bg-background">
      <Sidebar />
      <div className="lg:ml-[15rem]">
        <TopBar />
        <main className="mx-auto max-w-[100rem] p-5 lg:px-12 lg:py-10" data-testid="main-content">
          {children}
        </main>
      </div>
    </div>
  );
}
