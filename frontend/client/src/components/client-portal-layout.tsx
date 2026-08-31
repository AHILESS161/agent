import { Link, useLocation } from "wouter";
import { Bell, ChevronDown, LogOut, UserRound } from "lucide-react";
import { BrandWordmark } from "@/components/brand-wordmark";
import { Button } from "@/components/ui/button";
import { Avatar, AvatarFallback } from "@/components/ui/avatar";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuLabel,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { useAuth } from "@/lib/auth";
import { useUnreadCount } from "@/lib/use-unread-count";
import { cn } from "@/lib/utils";
import { ClientAssistant } from "@/components/client-assistant";

export function ClientPortalLayout({ children }: { children: React.ReactNode }) {
  const { user, logout } = useAuth();
  const [location, setLocation] = useLocation();
  const unread = useUnreadCount();
  const initials = (user?.fullName || user?.email || "?")
    .split(/\s+/)
    .map((part) => part[0])
    .join("")
    .slice(0, 2)
    .toUpperCase();

  const links = [
    { href: "/dashboard", label: "Мои заявки" },
    { href: "/how-it-works", label: "Как это работает" },
  ];

  return (
    <div className="min-h-screen bg-[#f6f5f1] text-[#11113f]">
      <header className="sticky top-0 z-30 border-b border-[#11113f]/10 bg-[#fbfaf7]/95 backdrop-blur">
        <div className="mx-auto flex h-20 max-w-[92rem] items-center gap-6 px-5 sm:px-8 lg:px-12">
          <Link href="/dashboard">
            <div className="cursor-pointer text-[1.8rem] leading-none text-[#11113f]">
              <BrandWordmark accentEnd />
            </div>
          </Link>

          <nav className="hidden items-center gap-1 md:flex">
            {links.map((item) => {
              const active =
                location === item.href ||
                (item.href === "/dashboard" && location.startsWith("/applications/"));
              return (
                <Link key={item.href} href={item.href}>
                  <span
                    className={cn(
                      "cursor-pointer rounded-full px-4 py-2 text-sm font-semibold transition-colors",
                      active
                        ? "bg-[#11113f] text-white"
                        : "text-[#55556f] hover:bg-white hover:text-[#11113f]",
                    )}
                  >
                    {item.label}
                  </span>
                </Link>
              );
            })}
          </nav>

          <div className="ml-auto flex items-center gap-2 sm:gap-3">
            <Button
              variant="ghost"
              size="icon"
              className="relative rounded-full text-[#11113f]"
              onClick={() => setLocation("/notifications")}
              aria-label="Уведомления"
            >
              <Bell className="h-5 w-5" />
              {unread > 0 && (
                <span className="absolute right-2 top-2 h-2 w-2 rounded-full bg-[#ef5b62]" />
              )}
            </Button>

            <DropdownMenu>
              <DropdownMenuTrigger asChild>
                <Button variant="ghost" className="h-11 gap-2 rounded-full px-1.5 sm:px-2">
                  <Avatar className="h-9 w-9 border border-[#11113f]/15 bg-white">
                    <AvatarFallback className="bg-white text-xs font-semibold text-[#11113f]">
                      {initials}
                    </AvatarFallback>
                  </Avatar>
                  <ChevronDown className="hidden h-4 w-4 text-[#6d6d7d] sm:block" />
                </Button>
              </DropdownMenuTrigger>
              <DropdownMenuContent align="end" className="w-64">
                <DropdownMenuLabel>
                  <p className="font-semibold">{user?.fullName}</p>
                  <p className="mt-1 text-xs font-normal text-muted-foreground">{user?.email}</p>
                </DropdownMenuLabel>
                <DropdownMenuSeparator />
                <DropdownMenuItem onClick={() => setLocation("/profile")}>
                  <UserRound className="mr-2 h-4 w-4" /> Мои данные
                </DropdownMenuItem>
                <DropdownMenuItem onClick={logout}>
                  <LogOut className="mr-2 h-4 w-4" /> Выйти
                </DropdownMenuItem>
              </DropdownMenuContent>
            </DropdownMenu>
          </div>
        </div>
      </header>

      <main className="mx-auto max-w-[92rem] px-5 py-8 sm:px-8 lg:px-12 lg:py-12" data-testid="client-main">
        {children}
      </main>

      <footer className="mt-12 border-t border-[#11113f]/10 bg-[#fbfaf7]">
        <div className="mx-auto flex max-w-[92rem] flex-col gap-2 px-5 py-7 text-sm text-[#6d6d7d] sm:flex-row sm:items-center sm:justify-between sm:px-8 lg:px-12">
          <span>Регистр — регистрация товарного знака по понятным шагам</span>
          <span>Результат проверки носит предварительный характер</span>
        </div>
      </footer>
      <ClientAssistant />
    </div>
  );
}
