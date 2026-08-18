import { useState } from "react";
import { useAuth } from "@/lib/auth";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import {
  AlertCircle,
  BriefcaseBusiness,
  Check,
  Eye,
  EyeOff,
  Loader2,
  LockKeyhole,
  ShieldCheck,
  UserRound,
  UsersRound,
} from "lucide-react";
import { BrandWordmark } from "@/components/brand-wordmark";

type DemoRole = "client" | "lawyer" | "admin";

const DEMO_ROLES = [
  {
    id: "client" as const,
    label: "Клиент",
    description: "Создать и отслеживать заявку",
    email: "client@demo.ru",
    icon: UserRound,
    order: 1,
  },
  {
    id: "admin" as const,
    label: "Администратор",
    description: "Распределять заявки и управлять системой",
    email: "admin@demo.ru",
    icon: UsersRound,
    order: 3,
  },
  {
    id: "lawyer" as const,
    label: "Юрист",
    description: "Проверять заявки и заключения",
    email: null,
    icon: BriefcaseBusiness,
    order: 2,
  },
];

const DEMO_LAWYERS = [
  { email: "bogdan@demo.ru", label: "Богдан" },
  { email: "dasha@demo.ru", label: "Даша" },
];
const DEMO_PASSWORD = "demo123";

export default function LoginPage() {
  const { login } = useAuth();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [showPassword, setShowPassword] = useState(false);
  const [remember, setRemember] = useState(true);
  const [error, setError] = useState("");
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [demoRole, setDemoRole] = useState<DemoRole | null>(null);
  const [demoEmail, setDemoEmail] = useState<string | null>(null);

  const submit = async (loginEmail: string, loginPassword: string) => {
    setError("");
    if (!loginEmail.trim()) return setError("Введите адрес электронной почты");
    if (!loginPassword) return setError("Введите пароль");
    setIsSubmitting(true);
    try {
      const message = await login(loginEmail, loginPassword);
      if (message) setError(message);
    } finally {
      setIsSubmitting(false);
    }
  };

  const chooseDemoRole = (role: DemoRole, accountEmail: string | null) => {
    setDemoRole(role);
    setDemoEmail(accountEmail);
    setEmail(accountEmail || "");
    setPassword(DEMO_PASSWORD);
    setError("");
  };

  const chooseLawyer = (accountEmail: string) => {
    setDemoEmail(accountEmail);
    setEmail(accountEmail);
    setPassword(DEMO_PASSWORD);
    setError("");
  };

  return (
    <main className="grid min-h-screen bg-[#f7f5f1] lg:grid-cols-[1.04fr_.96fr]">
      <section className="relative hidden overflow-hidden border-r border-black/5 px-[8vw] py-16 lg:flex lg:flex-col lg:justify-center">
        <div className="absolute left-[8vw] top-12 text-[1.7rem] text-[#17104f]">
          <BrandWordmark accentEnd />
        </div>

        <div className="max-w-[650px]">
          <div className="flex items-end gap-4">
            <h1 className="text-[clamp(74px,8vw,132px)] leading-[.82] text-[#17104f]">
              <BrandWordmark />
            </h1>
            <span className="mb-1 flex h-11 w-11 items-center justify-center rounded-full bg-primary text-white">
              <LockKeyhole className="h-5 w-5" />
            </span>
          </div>

          <div className="relative mt-7 border-t-[3px] border-primary pt-8">
            <div className="absolute -right-7 -top-[3px] h-[168px] w-8 rounded-r-[28px] border-y-[3px] border-r-[3px] border-primary" />
            <h2 className="text-[34px] font-semibold leading-[1.08] text-[#17104f]">
              Защищаем идеи.<br />Управляем правами
            </h2>
            <p className="mt-4 max-w-md text-[20px] leading-snug text-[#5e5e68]">
              Регистрация товарных знаков —<br />от заявки до свидетельства.
            </p>
          </div>
        </div>

        <div className="absolute bottom-16 left-[8vw] flex items-center gap-7 text-sm text-[#4f5058]">
          <span>Заявители</span><span className="text-primary">/</span>
          <span>Товарные знаки</span><span className="text-primary">/</span>
          <span>Документы</span>
        </div>
      </section>

      <section className="flex items-center justify-center bg-[#08090b] p-5 sm:p-8 xl:p-10">
        <div className="w-full max-w-[620px] rounded-[18px] bg-[#fbfaf8] p-6 shadow-2xl sm:p-8 xl:p-9">
          <div className="mb-6 flex border-b border-border text-center text-sm">
            <div className="relative flex-1 pb-4 font-medium text-[#17104f] after:absolute after:inset-x-0 after:bottom-[-1px] after:h-[3px] after:bg-primary">
              Вход
            </div>
            <div className="flex-1 pb-4 text-muted-foreground" title="Регистрация доступна администратору">
              Доступ по приглашению
            </div>
          </div>

          <h2 className="text-2xl font-semibold text-[#17104f]">Войти в систему</h2>
          <p className="mt-2 text-sm text-muted-foreground">Используйте рабочую учётную запись</p>

          <form
            className="mt-5 space-y-4"
            onSubmit={(event) => {
              event.preventDefault();
              void submit(email, password);
            }}
          >
            <div className="space-y-2">
              <Label htmlFor="email">Логин</Label>
              <Input
                id="email"
                type="email"
                value={email}
                onChange={(event) => setEmail(event.target.value)}
                placeholder="name@company.ru"
                autoComplete="username"
                disabled={isSubmitting}
                className="h-12 bg-transparent"
                data-testid="input-email"
              />
            </div>
            <div className="space-y-2">
              <Label htmlFor="password">Пароль</Label>
              <div className="relative">
                <Input
                  id="password"
                  type={showPassword ? "text" : "password"}
                  value={password}
                  onChange={(event) => setPassword(event.target.value)}
                  placeholder="••••••••••"
                  autoComplete="current-password"
                  disabled={isSubmitting}
                  className="h-12 bg-transparent pr-12"
                  data-testid="input-password"
                />
                <button
                  type="button"
                  onClick={() => setShowPassword((value) => !value)}
                  className="absolute right-4 top-1/2 -translate-y-1/2 text-muted-foreground hover:text-foreground"
                  aria-label={showPassword ? "Скрыть пароль" : "Показать пароль"}
                >
                  {showPassword ? <EyeOff className="h-4 w-4" /> : <Eye className="h-4 w-4" />}
                </button>
              </div>
            </div>

            <label className="flex cursor-pointer items-center gap-2 text-sm text-muted-foreground">
              <button
                type="button"
                onClick={() => setRemember((value) => !value)}
                className="flex h-5 w-5 items-center justify-center rounded border border-primary text-primary"
                aria-pressed={remember}
              >
                {remember && <Check className="h-3.5 w-3.5" />}
              </button>
              Запомнить меня
            </label>

            {error && (
              <div className="flex items-center gap-2 text-sm text-destructive" data-testid="login-error">
                <AlertCircle className="h-4 w-4" /> {error}
              </div>
            )}

            <Button type="submit" className="h-12 w-full text-sm" disabled={isSubmitting} data-testid="button-login">
              {isSubmitting && <Loader2 className="h-4 w-4 animate-spin" />}
              {isSubmitting ? "Входим…" : "Войти"}
            </Button>
          </form>

          <div className="mt-5 border-t border-border pt-5">
            <p className="text-center text-sm font-medium text-[#17104f]">Или выберите тип аккаунта</p>
            <p className="mt-1 text-center text-xs text-muted-foreground">Для быстрого входа в демо-стенд</p>

            <div className="mt-4 grid gap-2 sm:grid-cols-3">
              {DEMO_ROLES.map((role) => {
                const Icon = role.icon;
                const selected = demoRole === role.id;
                return (
                  <button
                    key={role.id}
                    type="button"
                    disabled={isSubmitting}
                    onClick={() => chooseDemoRole(role.id, role.email)}
                    style={{ order: role.order }}
                    className={`rounded-xl border px-3 py-3 text-left transition ${
                      selected
                        ? "border-primary bg-primary/10 shadow-sm"
                        : "border-border bg-white hover:border-primary/50 hover:bg-primary/[0.04]"
                    }`}
                    aria-pressed={selected}
                    data-testid={`demo-role-${role.id}`}
                  >
                    <Icon className={`h-5 w-5 ${selected ? "text-primary" : "text-[#17104f]"}`} />
                    <span className="mt-2 block text-sm font-semibold text-[#17104f]">{role.label}</span>
                    <span className="mt-1 hidden text-[11px] leading-snug text-muted-foreground sm:block">{role.description}</span>
                  </button>
                );
              })}
            </div>

            {demoRole === "lawyer" && (
              <div className="mt-3 rounded-xl border border-primary/25 bg-primary/[0.05] p-3">
                <p className="mb-2 text-xs font-medium text-[#17104f]">Выберите юриста</p>
                <div className="grid grid-cols-2 gap-2">
                  {DEMO_LAWYERS.map((lawyer) => (
                    <button
                      key={lawyer.email}
                      type="button"
                      disabled={isSubmitting}
                      onClick={() => chooseLawyer(lawyer.email)}
                      className={`rounded-lg border px-3 py-2 text-sm font-medium transition ${
                        demoEmail === lawyer.email
                          ? "border-primary bg-primary text-white"
                          : "border-border bg-white text-[#17104f] hover:border-primary/50"
                      }`}
                      aria-pressed={demoEmail === lawyer.email}
                      data-testid={`demo-${lawyer.email.split("@")[0]}`}
                    >
                      {lawyer.label}
                    </button>
                  ))}
                </div>
              </div>
            )}

            <Button
              type="button"
              className="mt-3 h-11 w-full"
              disabled={isSubmitting || !demoEmail}
              onClick={() => demoEmail && void submit(demoEmail, DEMO_PASSWORD)}
              data-testid="button-demo-login"
            >
              {isSubmitting && <Loader2 className="h-4 w-4 animate-spin" />}
              {demoRole === "lawyer" && demoEmail
                ? `Войти как ${DEMO_LAWYERS.find((item) => item.email === demoEmail)?.label}`
                : demoRole
                  ? `Войти как ${DEMO_ROLES.find((item) => item.id === demoRole)?.label.toLowerCase()}`
                  : "Сначала выберите аккаунт"}
            </Button>
          </div>

          <p className="mt-7 flex items-center justify-center gap-2 text-xs text-muted-foreground">
            <ShieldCheck className="h-4 w-4 text-primary" /> Защищённое соединение · демо-режим
          </p>
        </div>
      </section>
    </main>
  );
}
