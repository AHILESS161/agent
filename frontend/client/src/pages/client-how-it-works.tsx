import { useLocation } from "wouter";
import { Button } from "@/components/ui/button";
import {
  ArrowRight,
  BadgeRussianRuble,
  CheckCircle2,
  FileArchive,
  FileSearch,
  FolderUp,
  Landmark,
} from "lucide-react";

const STEPS = [
  {
    icon: FolderUp,
    title: "1. Добавьте исходные данные",
    userAction: "Опишите знак и деятельность, загрузите доступные документы и изображение обозначения.",
    serviceAction: "Распознаем сведения из файлов, заполним доступные поля и покажем их вам для проверки.",
  },
  {
    icon: FileSearch,
    title: "2. Выберите товары, услуги и классы МКТУ",
    userAction: "Проверьте предложенные направления и подтвердите товары и услуги, для которых нужна охрана.",
    serviceAction: "Предложим классы МКТУ по вашему описанию и объясним, почему они подходят.",
  },
  {
    icon: CheckCircle2,
    title: "3. Мы оценим риски отказа",
    userAction: "Проверьте исходные данные и при необходимости уточните обозначение или перечень товаров и услуг.",
    serviceAction: "Сначала проверим абсолютные основания для отказа, затем найдём сходные знаки в подтверждённых классах и объясним результат понятным языком.",
  },
  {
    icon: BadgeRussianRuble,
    title: "4. Мы рассчитаем пошлины",
    userAction: "Укажите способ подачи, необходимость бумажного свидетельства и специальное основание для льготы, если оно есть.",
    serviceAction: "Покажем платежи по этапам, объясним, из чего сложилась сумма, и сверим расчёт с официальными правилами.",
  },
  {
    icon: FileArchive,
    title: "5. Мы подготовим пакет документов",
    userAction: "Дополните недостающие сведения и проверьте заявление в окне предпросмотра.",
    serviceAction: "Соберём заявление, необходимые приложения, контрольный список и понятную памятку по подаче.",
  },
  {
    icon: Landmark,
    title: "6. Подайте заявку в Роспатент",
    userAction: "Подпишите и отправьте готовый комплект через официальный сервис Роспатента, затем следите за уведомлениями.",
    serviceAction: "Сохраним документы в деле, а если придёт запрос или уведомление — поможем разобрать его и подготовить проект ответа.",
  },
];

export default function ClientHowItWorksPage() {
  const [, setLocation] = useLocation();

  return (
    <div className="mx-auto max-w-5xl space-y-8" data-testid="client-how-it-works">
      <header className="rounded-[2rem] bg-[#11113f] px-7 py-10 text-white sm:px-12 sm:py-14">
        <p className="text-sm font-bold uppercase tracking-[.16em] text-[#43c7c2]">Путь к регистрации</p>
        <h1 className="mt-4 max-w-3xl text-4xl font-semibold leading-tight sm:text-5xl">Как зарегистрировать товарный знак с Регистром</h1>
        <p className="mt-5 max-w-3xl text-base leading-relaxed text-white/75 sm:text-lg">
          От исходных данных до комплекта для подачи — по шагам, с пояснениями и возможностью проверить каждое автоматически подготовленное значение.
        </p>
      </header>

      <section className="grid gap-4 md:grid-cols-2">
        {STEPS.map((step) => (
          <article key={step.title} className="rounded-[1.5rem] border border-[#11113f]/10 bg-white p-6 sm:p-7">
            <span className="flex h-11 w-11 items-center justify-center rounded-full bg-[#e8f7f6] text-[#0d9f9b]">
              <step.icon className="h-5 w-5" />
            </span>
            <h2 className="mt-5 text-xl font-semibold text-[#11113f]">{step.title}</h2>
            <div className="mt-5 space-y-3">
              <div className="rounded-2xl bg-[#f7f7f5] px-4 py-3.5">
                <p className="text-xs font-bold uppercase tracking-[.12em] text-[#616176]">Что делаете вы</p>
                <p className="mt-1.5 text-sm leading-6 text-[#313148]">{step.userAction}</p>
              </div>
              <div className="rounded-2xl border border-[#0d9f9b]/15 bg-[#eaf8f7] px-4 py-3.5">
                <p className="text-xs font-bold uppercase tracking-[.12em] text-[#078984]">Что делает сервис</p>
                <p className="mt-1.5 text-sm leading-6 text-[#315c5a]">{step.serviceAction}</p>
              </div>
            </div>
          </article>
        ))}
      </section>

      <section className="rounded-[1.5rem] border border-[#0d9f9b]/25 bg-[#eaf8f7] p-7 sm:flex sm:items-center sm:justify-between sm:gap-8">
        <div>
          <h2 className="text-2xl font-semibold text-[#11113f]">Готовы начать?</h2>
          <p className="mt-2 text-sm leading-relaxed text-[#616176]">Черновик сохраняется: можно остановиться и продолжить позже.</p>
        </div>
        <Button className="mt-5 rounded-full bg-[#0d9f9b] px-6 text-white hover:bg-[#078984] sm:mt-0" onClick={() => setLocation("/start")}>
          Начать проверку <ArrowRight className="h-4 w-4" />
        </Button>
      </section>
    </div>
  );
}
