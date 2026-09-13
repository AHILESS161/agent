import type { ReactNode } from "react";
import { Link } from "wouter";
import { ArrowUpRight } from "lucide-react";
import gods from "@/assets/three-gods.png";
import { BrandWordmark } from "@/components/brand-wordmark";
import { Button } from "@/components/ui/button";

export function AuthLayout({ children, view }: { children: ReactNode; view: "login" | "signup" }) {
  return <main className={`client-light-scope registr-v3 registr-auth-shell registr-auth-${view}`}>
    <section className="registr-auth-intro" aria-label="Регистр">
      <Link href="/?section=top" className="registr-auth-logo" aria-label="Регистр — главная"><BrandWordmark /></Link>
      <div className="registr-auth-content">
        <div className="registr-auth-message">
          <h1 className="registr-serif">Защищаем идеи - <em>управляем правами</em></h1>
          <p>Регистрация товарных знаков - от заявки до свидетельства</p>
        </div>
        <div className="registr-auth-visual">
          <div className="registr-auth-art" aria-hidden="true"><img src={gods} alt="" width="1897" height="829" /></div>
          <Button asChild variant="outline" className="registr-auth-about"><Link href="/?section=top">О Регистре<ArrowUpRight aria-hidden="true" /></Link></Button>
        </div>
      </div>
    </section>
    <section className="login-panel registr-auth-panel" aria-label={view === "login" ? "Вход в Регистр" : "Регистрация в Регистре"}>
      <div className="login-card registr-auth-card">{children}</div>
    </section>
  </main>;
}
