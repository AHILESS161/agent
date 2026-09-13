import { useEffect } from "react";
import { HomeSectionLink, PublicFooter, PublicHeader } from "@/components/public-layout";
import themis from "@/assets/principles/themis.png";
import plutus from "@/assets/principles/plutus.png";
import tyche from "@/assets/principles/tyche.png";
import "@/styles/landing.css";
import "@/styles/principles.css";

const principles = [
  {
    id: "themis", name: "Фемида", image: themis,
    alt: "Фемида с весами и мечом — светлая мраморная скульптура на фоне золотых цифровых связей",
    title: "Честная оценка",
    symbol: "Весы Фемиды — наш образ взвешенного решения.",
    description: "Объясняем, на чём основан вывод: какие риски есть у обозначения и где остаётся неопределённость. Понятные основания помогают принять решение без ложных ожиданий.",
    practice: "Причины риска и ограничения проверки — рядом с результатом.",
  },
  {
    id: "plutus", name: "Плутос", image: plutus,
    alt: "Плутос с рогом изобилия — светлая мраморная скульптура на фоне золотых цифровых связей",
    title: "Ценность бренда",
    symbol: "Рог изобилия Плутоса — образ ценности, которую вы создаёте.",
    description: "За названием стоят ваш труд, репутация и планы на рост. Рассматриваем обозначение в контексте бизнеса, чтобы подготовка к регистрации начиналась с того, что вы хотите защитить.",
    practice: "Товары и услуги — исходя из вашей деятельности.",
  },
  {
    id: "tyche", name: "Тюхе", image: tyche,
    alt: "Тюхе с короной и рулевым веслом — светлая мраморная скульптура на фоне золотых цифровых связей",
    title: "Осознанный выбор",
    symbol: "Рулевое весло Тюхе — образ выбора курса в неопределённости.",
    description: "Будущее нельзя предсказать, но к решению можно подготовиться. Помогаем сопоставить варианты и увидеть следующие шаги. Вы выбираете, с каким названием двигаться дальше.",
    practice: "Сравнение обозначений — с объяснением сильных сторон и рисков.",
  },
];

export default function PrinciplesPage() {
  useEffect(() => { window.scrollTo({ top: 0 }); }, []);

  return (
    <div className="client-light-scope registr-v3 landing-v3 principles-page">
      <div className="page-shell">
        <PublicHeader principles />
        <main>
          <section className="principles-intro" aria-labelledby="principles-title">
            <span className="section-kicker">Принципы сервиса</span>
            <h1 id="principles-title">Три принципа.<br /><em>Одна цель — защита.</em></h1>
            <p>Античные образы вдохновляют наш подход.<br className="desktop-break" /> Современные технологии помогают воплощать его в работе с вашим брендом.</p>
          </section>
          <div className="principles-grid">
            {principles.map((principle, index) => (
              <article className="principle" key={principle.id} aria-labelledby={`${principle.id}-title`}>
                <div className="principle-art">
                  <img src={principle.image} width="1122" height="1402" alt={principle.alt} decoding="async" />
                </div>
                <div className="principle-copy">
                  <p className="principle-label"><span>0{index + 1}</span><span>{principle.name}</span></p>
                  <h2 id={`${principle.id}-title`}>{principle.title}</h2>
                  <p className="principle-symbol">{principle.symbol}</p>
                  <p className="principle-description">{principle.description}</p>
                  <p className="principle-practice">{principle.practice}</p>
                </div>
              </article>
            ))}
          </div>
          <section className="principles-next" aria-label="Продолжить знакомство с сервисом">
            <p>От принципов — к вашему бренду.</p>
            <HomeSectionLink section="approach" className="button button-dark">Как это работает <span aria-hidden="true">↗</span></HomeSectionLink>
          </section>
        </main>
        <PublicFooter />
      </div>
    </div>
  );
}
