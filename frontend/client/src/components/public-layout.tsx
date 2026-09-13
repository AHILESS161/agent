import type { ReactNode } from "react";
import { Link } from "wouter";
import { useAuth } from "@/lib/auth";
import { BrandWordmark } from "@/components/brand-wordmark";

export function HomeSectionLink({ section, children, className }: { section: string; children: ReactNode; className?: string }) {
  return <Link href={`/?section=${section}`} className={className}>{children}</Link>;
}

export function PublicHeader({ principles = false }: { principles?: boolean }) {
  const { user } = useAuth();

  return (
    <header className="header">
      <HomeSectionLink section="top" className="wordmark"><BrandWordmark /></HomeSectionLink>
      <nav aria-label="Основная навигация">
        <Link href="/principles" aria-current={principles ? "page" : undefined}>Принципы сервиса</Link>
        <HomeSectionLink section="approach">Как это работает</HomeSectionLink>
        <HomeSectionLink section="result">Результат</HomeSectionLink>
        <HomeSectionLink section="questions">Вопросы</HomeSectionLink>
      </nav>
      <Link className="button button-small button-dark" href={user ? "/dashboard" : "/login"}>Личный кабинет <span aria-hidden="true">↗</span></Link>
    </header>
  );
}

export function PublicFooter() {
  return (
    <footer className="footer">
      <HomeSectionLink section="top" className="wordmark"><BrandWordmark /></HomeSectionLink>
      <p>Проверка обозначения и подготовка заявки на товарный знак</p>
      <Link className="footer-services" href="/services">Ответы и сравнение ↗</Link>
    </footer>
  );
}
