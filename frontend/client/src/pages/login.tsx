import { useState } from "react";
import { useAuth } from "@/lib/auth";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { AlertCircle, Check, Eye, EyeOff, Loader2, LockKeyhole, ShieldCheck } from "lucide-react";
import { BrandWordmark } from "@/components/brand-wordmark";

const DEMO_USERS = [
  { email: "lawyer@demo.ru", label: "Юрист" },
  { email: "admin@demo.ru", label: "Администратор" },
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

      <section className="flex items-center justify-center bg-[#08090b] p-5 sm:p-10">
        <div className="w-full max-w-[500px] rounded-xl bg-[#fbfaf8] p-7 shadow-2xl sm:p-10">
          <div className="mb-9 flex border-b border-border text-center text-sm">
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
            className="mt-7 space-y-5"
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

          <div className="mt-7 border-t border-border pt-6">
            <p className="mb-3 text-center text-xs text-muted-foreground">Быстрый вход в демо-стенд</p>
            <div className="grid grid-cols-2 gap-2">
              {DEMO_USERS.map((user) => (
                <Button
                  key={user.email}
                  type="button"
                  variant="outline"
                  disabled={isSubmitting}
                  onClick={() => {
                    setEmail(user.email);
                    setPassword(DEMO_PASSWORD);
                    void submit(user.email, DEMO_PASSWORD);
                  }}
                  data-testid={`demo-${user.email.split("@")[0]}`}
                >
                  {user.label}
                </Button>
              ))}
            </div>
          </div>

          <p className="mt-7 flex items-center justify-center gap-2 text-xs text-muted-foreground">
            <ShieldCheck className="h-4 w-4 text-primary" /> Защищённое соединение · демо-режим
          </p>
        </div>
      </section>
    </main>
  );
}
