import { useEffect, useState } from "react";
import { Link } from "wouter";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { BrandWordmark } from "@/components/brand-wordmark";
import { Loader2, MailCheck } from "lucide-react";

export default function SignupPage({ verify = false }: { verify?: boolean }) {
  const [email, setEmail] = useState("");
  const [name, setName] = useState("");
  const [password, setPassword] = useState("");
  const [confirmation, setConfirmation] = useState("");
  const [enabled, setEnabled] = useState<boolean | null>(null);
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState("");
  const [error, setError] = useState("");
  const [complete, setComplete] = useState(false);
  const [cooldown, setCooldown] = useState(0);
  const [token] = useState(() => new URLSearchParams(window.location.hash.split("?")[1] || "").get("token") || "");

  useEffect(() => {
    fetch("/api/v1/auth/signup/config", { cache: "no-store" })
      .then(r => r.ok ? r.json() : Promise.reject())
      .then(data => setEnabled(data.enabled === true))
      .catch(() => setEnabled(false));
  }, []);
  useEffect(() => {
    if (!cooldown) return;
    const timer = setTimeout(() => setCooldown(cooldown - 1), 1000);
    return () => clearTimeout(timer);
  }, [cooldown]);

  async function submit() {
    if (busy) return;
    setError("");
    if (verify && password !== confirmation) { setError("Пароли не совпадают"); return; }
    if (verify && !token) { setError("В ссылке нет кода подтверждения. Запросите новое письмо."); return; }
    setBusy(true);
    try {
      const response = await fetch(`/api/v1/auth/signup/${verify ? "confirm" : "request"}`, {
        method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify(verify ? { token, password, full_name: name.trim() } : { email: email.trim() }),
      });
      const data = await response.json();
      if (!response.ok) throw new Error(typeof data.detail === "string" ? data.detail : "Проверьте заполнение полей.");
      setMessage(data.message);
      if (verify) {
        setComplete(true); setPassword(""); setConfirmation("");
        window.history.replaceState(null, "", window.location.pathname + "#/verify-email");
      } else { setCooldown(60); }
    } catch (failure) {
      setError(failure instanceof Error ? failure.message : "Не удалось связаться с сервером.");
    } finally { setBusy(false); }
  }

  return <main className="flex min-h-[100svh] items-center justify-center bg-[#f7f5f1] p-5">
    <section className="w-full max-w-md rounded-2xl border bg-white p-7 shadow-sm">
      <div className="mb-7 text-3xl text-[#17104f]"><BrandWordmark accentEnd /></div>
      <h1 className="text-2xl font-semibold">{verify ? "Завершить регистрацию" : "Регистрация клиента"}</h1>
      <p className="mt-3 text-sm text-muted-foreground">{verify
        ? "Укажите имя и придумайте пароль для своего аккаунта."
        : "Укажите почту — отправим ссылку для подтверждения и создания пароля."}</p>
      {enabled === null && <p className="mt-5" role="status">Проверяем доступность…</p>}
      {enabled === false && <p className="mt-5 text-sm" role="alert">Регистрация временно недоступна. Попробуйте позже.</p>}
      {message && <div className="mt-5 rounded-lg bg-green-50 p-4 text-sm text-green-900" role="status"><MailCheck className="mb-2 h-5 w-5" />{message}</div>}
      {error && <p className="mt-4 text-sm text-destructive" role="alert">{error}</p>}
      {enabled && !complete && <form className="mt-6 space-y-4" onSubmit={event => { event.preventDefault(); void submit(); }}>
        {verify ? <>
          <div className="space-y-2"><Label htmlFor="signup-name">Имя</Label><Input id="signup-name" value={name} onChange={e => setName(e.target.value)} maxLength={255} autoComplete="name" required disabled={busy} /></div>
          <div className="space-y-2"><Label htmlFor="signup-password">Пароль</Label><Input id="signup-password" type="password" value={password} onChange={e => setPassword(e.target.value)} minLength={8} maxLength={1024} autoComplete="new-password" required disabled={busy} /><p className="text-xs text-muted-foreground">Не менее 8 символов.</p></div>
          <div className="space-y-2"><Label htmlFor="signup-confirmation">Повторите пароль</Label><Input id="signup-confirmation" type="password" value={confirmation} onChange={e => setConfirmation(e.target.value)} minLength={8} maxLength={1024} autoComplete="new-password" required disabled={busy} /></div>
        </> : <div className="space-y-2"><Label htmlFor="signup-email">Электронная почта</Label><Input id="signup-email" type="email" value={email} onChange={e => setEmail(e.target.value)} maxLength={255} autoComplete="email" placeholder="name@example.ru" required disabled={busy} /></div>}
        <Button className="w-full" disabled={busy || cooldown > 0 || (verify && !token)} type="submit">
          {busy && <Loader2 className="mr-2 h-4 w-4 animate-spin" />}
          {verify ? "Подтвердить почту и создать аккаунт" : cooldown ? `Повторить через ${cooldown} с` : message ? "Отправить письмо повторно" : "Получить ссылку"}
        </Button>
      </form>}
      {verify && !complete && <Link href="/signup" className="mt-5 block text-sm text-primary underline">Запросить новое письмо</Link>}
      <Link href="/" className="mt-6 block text-sm text-primary underline">{complete ? "Войти в аккаунт" : "Уже есть аккаунт? Войти"}</Link>
    </section>
  </main>;
}
