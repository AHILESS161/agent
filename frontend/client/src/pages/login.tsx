import { useState } from "react";
import { useAuth } from "@/lib/auth";
import { useTheme } from "@/lib/theme";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Card, CardContent, CardHeader } from "@/components/ui/card";
import { Label } from "@/components/ui/label";
import { Badge } from "@/components/ui/badge";
import { Moon, Sun, LogIn, AlertCircle, Loader2 } from "lucide-react";

// Учётные записи демо-стенда. Пароль настоящий и проверяется на сервере.
const DEMO_USERS = [
  { email: "lawyer@demo.ru", role: "Специалист (юрист)" },
  { email: "admin@demo.ru", role: "Администратор" },
];

const DEMO_PASSWORD = "demo123";

export default function LoginPage() {
  const { login } = useAuth();
  const { theme, toggleTheme } = useTheme();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");
  const [isSubmitting, setIsSubmitting] = useState(false);

  const submit = async (loginEmail: string, loginPassword: string) => {
    setError("");
    if (!loginEmail) {
      setError("Введите адрес электронной почты");
      return;
    }
    if (!loginPassword) {
      setError("Введите пароль");
      return;
    }
    setIsSubmitting(true);
    try {
      const message = await login(loginEmail, loginPassword);
      if (message) setError(message);
    } finally {
      setIsSubmitting(false);
    }
  };

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    void submit(email, password);
  };

  const handleDemoLogin = (demoEmail: string) => {
    setEmail(demoEmail);
    setPassword(DEMO_PASSWORD);
    void submit(demoEmail, DEMO_PASSWORD);
  };

  return (
    <div className="min-h-screen flex items-center justify-center bg-background p-4 relative">
      <div className="absolute top-4 right-4">
        <Button
          variant="ghost"
          size="icon"
          onClick={toggleTheme}
          className="h-8 w-8"
          data-testid="login-toggle-theme"
        >
          {theme === "dark" ? <Sun className="w-4 h-4" /> : <Moon className="w-4 h-4" />}
        </Button>
      </div>

      <div className="w-full max-w-sm">
        <div className="flex flex-col items-center mb-8">
          <svg viewBox="0 0 48 48" className="w-14 h-14 mb-3" fill="none" aria-label="ТМ Регистрация">
            <rect x="3" y="3" width="42" height="42" rx="10" stroke="hsl(174, 83%, 32%)" strokeWidth="3" />
            <text x="24" y="32" textAnchor="middle" fill="hsl(174, 83%, 32%)" fontSize="18" fontWeight="700" fontFamily="Inter, sans-serif">TM</text>
          </svg>
          <h1 className="text-xl font-bold text-foreground">ТМ Регистр</h1>
          <p className="text-sm text-muted-foreground mt-1">Система регистрации товарных знаков</p>
        </div>

        <Card className="border border-card-border">
          <CardHeader className="pb-4">
            <p className="text-sm font-semibold text-center">Вход в систему</p>
          </CardHeader>
          <CardContent>
            <form onSubmit={handleSubmit} className="space-y-4">
              <div className="space-y-1.5">
                <Label htmlFor="email" className="text-xs font-medium">Email</Label>
                <Input
                  id="email"
                  type="email"
                  placeholder="your@email.ru"
                  value={email}
                  onChange={e => setEmail(e.target.value)}
                  disabled={isSubmitting}
                  autoComplete="username"
                  data-testid="input-email"
                />
              </div>
              <div className="space-y-1.5">
                <Label htmlFor="password" className="text-xs font-medium">Пароль</Label>
                <Input
                  id="password"
                  type="password"
                  placeholder="••••••••"
                  value={password}
                  onChange={e => setPassword(e.target.value)}
                  disabled={isSubmitting}
                  autoComplete="current-password"
                  data-testid="input-password"
                />
              </div>

              {error && (
                <div className="flex items-center gap-2 text-sm text-destructive" data-testid="login-error">
                  <AlertCircle className="w-4 h-4" />
                  {error}
                </div>
              )}

              <Button
                type="submit"
                className="w-full"
                disabled={isSubmitting}
                data-testid="button-login"
              >
                {isSubmitting ? (
                  <>
                    <Loader2 className="w-4 h-4 mr-2 animate-spin" />
                    Вход…
                  </>
                ) : (
                  <>
                    <LogIn className="w-4 h-4 mr-2" />
                    Войти
                  </>
                )}
              </Button>
            </form>

            <div className="mt-6">
              <p className="text-xs text-muted-foreground text-center mb-3">
                Учётные записи демо-стенда (пароль {DEMO_PASSWORD}):
              </p>
              <div className="grid grid-cols-2 gap-2">
                {DEMO_USERS.map(u => (
                  <button
                    key={u.email}
                    type="button"
                    disabled={isSubmitting}
                    onClick={() => handleDemoLogin(u.email)}
                    className="flex flex-col items-start p-2 rounded-md border border-border hover:bg-accent transition-colors text-left"
                    data-testid={`demo-${u.email.split("@")[0]}`}
                  >
                    <span className="text-[11px] font-mono text-muted-foreground">{u.email}</span>
                    <span className="text-xs font-medium">{u.role}</span>
                  </button>
                ))}
              </div>
            </div>

            <p className="mt-6 text-[11px] leading-relaxed text-muted-foreground text-center">
              Демонстрационный стенд. Результаты формируются с применением
              автоматической обработки и носят предварительный информационный
              характер. Они требуют проверки специалистом. Заявка в Роспатент
              не подаётся.
            </p>
          </CardContent>
        </Card>
      </div>
    </div>
  );
}
