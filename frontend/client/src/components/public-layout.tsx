import type { ReactNode } from "react";
import { Link } from "wouter";
import { useAuth } from "@/lib/auth";
import { BrandWordmark } from "@/components/brand-wordmark";

export function HomeSectionLink({ section, children, className }: { section: string; children: ReactNode; className?: string }) {
  return <Link href={`/about?section=${section}`} className={className}>{children}</Link>;
}

export function PublicHeader() {
  const { user } = useAuth();

  return (
    <header className="header">
      <HomeSectionLink section="top" className="wordmark"><BrandWordmark /></HomeSectionLink>
      <nav aria-label="Основная навигация">
        <HomeSectionLink section="approach">Как это работает</HomeSectionLink>
        <HomeSectionLink section="result">Результат</HomeSectionLink>
        <HomeSectionLink section="questions">Вопросы</HomeSectionLink>
      </nav>
      <Link className="button button-small button-dark" href={user ? "/dashboard" : "/login"}>{user ? "Личный кабинет" : "Вход / Регистрация"} <span aria-hidden="true">↗</span></Link>
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
