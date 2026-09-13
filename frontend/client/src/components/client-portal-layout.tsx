import { Link, useLocation, useSearch } from "wouter";
import { useHashLocation } from "wouter/use-hash-location";
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
import { readServiceRoute, serviceHref } from "@/lib/service-navigation";

export function ClientPortalLayout({ children }: { children: React.ReactNode }) {
  const { user, logout } = useAuth();
  const [location, setLocation] = useLocation();
  const [hashLocation] = useHashLocation();
  const search = useSearch();
  const serviceRoute = readServiceRoute(hashLocation, search);
  const unread = useUnreadCount();
  const initials = (user?.fullName || user?.email || "?")
    .split(/\s+/)
    .map((part) => part[0])
    .join("")
    .slice(0, 2)
    .toUpperCase();

  const links = [
    {
      href: "/dashboard",
      label: "Мои заявки",
      active: location === "/dashboard" || location === "/start" || location.startsWith("/applications/"),
    },
    {
      href: serviceHref("reply", serviceRoute.applicationId),
      label: "Ответ Роспатенту",
      active: location === "/services" && serviceRoute.tool === "reply",
    },
    {
      href: serviceHref("compare", serviceRoute.applicationId),
      label: "Сравнение обозначений",
      active: location === "/services" && serviceRoute.tool === "compare",
    },
  ];

  return (
    <div className="client-light-scope registr-v3 min-h-screen bg-[#cebb9e] p-0 sm:p-5 lg:p-8">
      <div className="mx-auto min-h-screen max-w-[1512px] bg-[#fcfbf8] pb-1 sm:rounded-3xl">
      <header className="sticky top-0 z-30 bg-[#fcfbf8]/95 p-3 backdrop-blur sm:rounded-t-3xl sm:p-5 lg:px-8">
        <div className="grid grid-cols-[minmax(0,1fr)_auto] items-center gap-x-4 gap-y-3 rounded-3xl border border-[#ece8e0] bg-white px-4 py-3 lg:grid-cols-[minmax(0,1fr)_auto_minmax(0,1fr)] lg:rounded-full lg:px-6">
          <Link href="/" className="justify-self-start" aria-label="Регистр — главная">
            <div className="cursor-pointer text-[1.8rem] leading-none text-[#38322e]">
              <BrandWordmark />
            </div>
          </Link>

          <nav className="col-span-2 row-start-2 grid w-full grid-cols-3 items-stretch gap-1 border-t border-[#ece8e0] pt-3 lg:col-span-1 lg:col-start-2 lg:row-start-1 lg:flex lg:w-auto lg:justify-center lg:border-0 lg:pt-0" aria-label="Личный кабинет">
            {links.map((item) => {
              return (
                <Link key={item.label} href={item.href} aria-current={item.active ? "page" : undefined}>
                  <span
                    className={cn(
                      "flex h-full min-h-10 cursor-pointer items-center justify-center rounded-2xl px-2 py-2 text-center text-[11px] font-medium leading-snug transition-colors sm:px-3 sm:text-xs lg:whitespace-nowrap lg:rounded-full lg:px-4 lg:text-sm",
                      item.active
                        ? "bg-[#584b41] text-white"
                        : "text-[#746e66] hover:bg-[#f4f1eb] hover:text-[#38322e]",
                    )}
                  >
                    {item.label}
                  </span>
                </Link>
              );
            })}
          </nav>

          <div className="col-start-2 row-start-1 flex items-center justify-self-end gap-2 sm:gap-3 lg:col-start-3">
            <Button
              variant="ghost"
              size="icon"
              className="relative rounded-full text-[#584b41]"
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
                <Button variant="ghost" className="h-11 gap-2 rounded-full px-1.5 sm:px-2" aria-label="Меню профиля">
                  <Avatar className="h-9 w-9 border border-[#ded9cf] bg-white">
                    <AvatarFallback className="bg-[#f4f1eb] text-xs font-semibold text-[#584b41]">
                      {initials}
                    </AvatarFallback>
                  </Avatar>
                  <ChevronDown className="hidden h-4 w-4 text-[#746e66] sm:block" />
                </Button>
              </DropdownMenuTrigger>
              <DropdownMenuContent align="end" className="client-light-scope registr-v3 w-64">
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

      <main className="mx-auto max-w-[92rem] px-5 py-6 sm:px-8 lg:px-14 lg:py-10" data-testid="client-main">
        {children}
      </main>

      <footer className="mx-5 mt-12 border-t border-[#ded9cf] sm:mx-8">
        <div className="mx-auto flex max-w-[92rem] flex-col gap-2 py-7 text-xs leading-6 text-[#746e66] sm:flex-row sm:items-center sm:justify-between">
          <span>Регистр — регистрация товарного знака по понятным шагам</span>
          <span>Результат проверки носит предварительный характер</span>
        </div>
      </footer>
      <ClientAssistant />
      </div>
    </div>
  );
}
