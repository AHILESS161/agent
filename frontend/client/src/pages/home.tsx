import { useEffect, useRef, useState, type FormEvent } from "react";
import { Link, useLocation, useSearch } from "wouter";
import { useHashLocation } from "wouter/use-hash-location";
import { useAuth } from "@/lib/auth";
import { BrandWordmark, BrandSymbol } from "@/components/brand-wordmark";
import { brandStartRoute, readBrandStart, saveBrandStart } from "@/lib/brand-start";
import gods from "@/assets/three-gods.png";
import "@/styles/landing.css";

function SectionLink({ section, children, className }: { section: string; children: React.ReactNode; className?: string }) {
  return <Link href={`/?section=${section}`} className={className}>{children}</Link>;
}

export default function HomePage() {
  const { user } = useAuth();
  const [, navigate] = useLocation();
  const [hashLocation] = useHashLocation();
  const routeSearch = useSearch();
  const section = new URLSearchParams(hashLocation.split("?")[1] || routeSearch).get("section");
  const [brand, setBrand] = useState("");
  const [business, setBusiness] = useState("");
  const [error, setError] = useState("");
  const brandInput = useRef<HTMLInputElement>(null);
  const businessInput = useRef<HTMLInputElement>(null);

  // The first visit after signup returns here; keep the visitor's two answers visible.
  useEffect(() => {
    const pending = readBrandStart(user?.id ?? null);
    if (pending) {
      setBrand(pending.brand);
      setBusiness(pending.business);
    }
  }, [user?.id]);

  useEffect(() => {
    if (!section) { window.scrollTo({ top: 0 }); return; }
    const target = document.getElementById(section);
    if (target) target.scrollIntoView({ behavior: "smooth", block: "start" });
  }, [section]);

  function start(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!brand.trim()) { setError("Укажите название бренда."); brandInput.current?.focus(); return; }
    if (!business.trim()) { setError("Расскажите, какие товары или услуги вы предлагаете."); businessInput.current?.focus(); return; }
    try {
      saveBrandStart(brand, business, user?.id ?? null);
      navigate(brandStartRoute(user?.role));
    } catch {
      setError("Не удалось сохранить введённые данные. Разрешите сохранение данных сайта в браузере и повторите.");
    }
  }

  return (
    <div className="client-light-scope registr-v3 landing-v3">
      <div className="page-shell">
        <header className="header">
          <SectionLink section="top" className="wordmark"><BrandWordmark /></SectionLink>
          <nav aria-label="Основная навигация">
            <SectionLink section="approach">Как это работает</SectionLink>
            <Link href="/services">Инструменты</Link>
            <SectionLink section="result">Результат</SectionLink>
            <SectionLink section="questions">Вопросы</SectionLink>
          </nav>
          <Link className="button button-small button-dark" href={user ? "/dashboard" : "/login"}>Личный кабинет <span aria-hidden="true">↗</span></Link>
        </header>

        <main id="top">
          <section className="hero" aria-labelledby="hero-title">
            <h1 id="hero-title">Ваш бренд.<br /><em>Под вашей защитой.</em></h1>
            <p className="hero-intro">Проверьте название, узнайте риски и подготовьте заявку<br className="desktop-break" /> на товарный знак. Начните с двух простых ответов.</p>
            <form className="brand-form" id="brand-form" onSubmit={start} noValidate>
              <div className="form-fields">
                <div className="field">
                  <label htmlFor="brand-name"><span>01</span> Название бренда</label>
                  <input ref={brandInput} id="brand-name" name="brand" value={brand} onChange={(event) => { setBrand(event.target.value); setError(""); }} placeholder="Например, Квелтаро" autoComplete="off" maxLength={180} required aria-describedby={error ? "brand-error" : undefined} />
                </div>
                <div className="field">
                  <label htmlFor="brand-business"><span>02</span> Товары или услуги</label>
                  <input ref={businessInput} id="brand-business" name="business" value={business} onChange={(event) => { setBusiness(event.target.value); setError(""); }} placeholder="Например, кафе и выпечка" autoComplete="off" maxLength={500} required aria-describedby={error ? "brand-error" : undefined} />
                </div>
                <button className="button button-dark submit-button" type="submit">Проверить бренд <span aria-hidden="true">↗</span></button>
              </div>
              {error && <p className="form-error" id="brand-error" role="alert">{error}</p>}
            </form>
            <p className="form-caption">Реквизиты и документы понадобятся только при подготовке заявки</p>
            <div className="architecture gods-hero"><img src={gods} width="1897" height="829" alt="Фемида с весами правосудия, Плутос с рогом изобилия и Тюхе с короной и рулевым веслом — три скульптуры из светлого мрамора" loading="eager" /></div>
            <div className="hero-baseline"><span>Технологии для уверенных решений</span><span className="baseline-line" /><span>Внимание к каждому обозначению</span></div>
          </section>

          <section className="approach section" id="approach" aria-labelledby="approach-title">
            <div className="section-heading">
              <span className="section-kicker">01 / Понятный процесс</span>
              <h2 id="approach-title">Вы знаете свой бизнес.<br /><em>Мы поможем с защитой.</em></h2>
              <p>Расскажите, что создаёте. Регистр переведёт описание на язык товаров, услуг и оснований для регистрации.</p>
              <SectionLink section="brand-form" className="text-link">Начать с названия <span aria-hidden="true">↗</span></SectionLink>
            </div>
            <div className="steps">
              <article className="step"><span className="step-number">01</span><div><h3>Опишите бренд</h3><p>Название и несколько слов о деятельности. Классы МКТУ предложим по вашему описанию.</p></div></article>
              <article className="step"><span className="step-number">02</span><div><h3>Разберитесь в рисках</h3><p>Покажем возможные основания отказа, найденные совпадения и ограничения проверки.</p></div></article>
              <article className="step"><span className="step-number">03</span><div><h3>Подготовьте заявку</h3><p>Когда решите продолжить, добавьте заявителя и получите документы для подачи.</p></div></article>
            </div>
          </section>

          <section className="result-section section" id="result" aria-labelledby="result-title">
            <div className="result-copy">
              <span className="section-kicker">02 / Решение по существу</span>
              <h2 id="result-title">За каждым названием —<br /><em>ваша большая идея.</em></h2>
              <p>Не нужно разбираться в десятках полей. Сначала — вывод и следующий шаг. Подробности — когда они нужны.</p>
              <ul className="benefits"><li>Товары и услуги понятным языком</li><li>Объяснение причин риска</li><li>Документы после вашего решения</li></ul>
            </div>
            <article className="report-preview" aria-label="Пример структуры результата проверки">
              <div className="report-top"><BrandWordmark className="mini-wordmark" /><span className="report-tag">Пример результата</span></div>
              <div className="report-title">Проверка обозначения</div>
              <p className="report-subtitle">Что вы увидите в своём заключении</p>
              <div className="report-row"><span className="report-index">01</span><div><h3>Уровень риска</h3><p>Краткий вывод и причины</p></div><span className="report-glyph" aria-hidden="true">↗</span></div>
              <div className="report-row"><span className="report-index">02</span><div><h3>Найденные совпадения</h3><p>Источники и значимые различия</p></div><span className="report-glyph" aria-hidden="true">↗</span></div>
              <div className="report-row"><span className="report-index">03</span><div><h3>Что делать дальше</h3><p>Рекомендации для вашего бренда</p></div><span className="report-glyph" aria-hidden="true">↗</span></div>
              <p className="report-footnote">Предварительная оценка не гарантирует решение Роспатента.</p>
            </article>
          </section>

          <section className="questions section" id="questions" aria-labelledby="questions-title">
            <div className="section-heading"><span className="section-kicker">03 / Перед началом</span><h2 id="questions-title">Меньше неизвестного.<br /><em>Больше ясности.</em></h2></div>
            <div className="faq-list">
              <details><summary>Что нужно для первой проверки?<span aria-hidden="true">+</span></summary><p>Название, которое вы хотите защитить, и описание товаров или услуг. Сведения о заявителе понадобятся позже, если вы решите готовить заявку.</p></details>
              <details><summary>Нужно ли самостоятельно выбирать МКТУ?<span aria-hidden="true">+</span></summary><p>Регистр предлагает классы и перечень товаров или услуг по вашему описанию. Вам останется проверить, что они соответствуют фактической и планируемой деятельности.</p></details>
              <details><summary>Можно ли проверить логотип?<span aria-hidden="true">+</span></summary><p>Да, в рабочем сервисе можно приложить изображение и указать товары или услуги. Для комбинированного знака важно проверить и текст, и графические элементы.</p></details>
              <details><summary>Проверка гарантирует регистрацию?<span aria-hidden="true">+</span></summary><p>Нет. Проверка помогает оценить риски и подготовиться к подаче. Окончательное решение принимает Роспатент по результатам экспертизы.</p></details>
            </div>
          </section>

          <section className="closing" aria-labelledby="closing-title"><div><span className="section-kicker">Начните с того, что важно</span><h2 id="closing-title">Дайте своей идее<br /><em>право на имя.</em></h2></div><SectionLink section="brand-form" className="button button-dark">Проверить название <span aria-hidden="true">↗</span></SectionLink><span className="closing-symbol" aria-hidden="true"><BrandSymbol /></span></section>
        </main>
        <footer className="footer"><SectionLink section="top" className="wordmark"><BrandWordmark /></SectionLink><p>Проверка обозначения и подготовка заявки на товарный знак</p><Link className="footer-services" href="/services">Ответы и сравнение ↗</Link></footer>
      </div>
    </div>
  );
}
