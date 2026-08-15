import { Link, useLocation } from "wouter";
import {
  ArrowRight,
  CheckCircle2,
  CircleDot,
  FileSearch,
  Loader2,
  Plus,
  ShieldCheck,
  Sparkles,
} from "lucide-react";
import { Button } from "@/components/ui/button";
import { useAuth } from "@/lib/auth";
import { useCases } from "@/lib/use-cases";
import type { Application, ApplicationStatus } from "@shared/schema";

const RESULT_STATUSES = new Set<ApplicationStatus>([
  "memo_approved",
  "document_generation",
  "document_approved",
  "submitted",
  "closed",
]);

function stageFor(status: ApplicationStatus) {
  if (["draft", "info_requested", "info_received"].includes(status)) {
    return { step: 1, label: status === "info_requested" ? "Нужны данные" : "Заполнение данных", action: "Продолжить заполнение" };
  }
  if (["classification_pending", "classification_review", "classification_approved"].includes(status)) {
    return { step: 2, label: status === "classification_review" ? "Подтвердите классы" : "Подбор классов МКТУ", action: "Проверить классы" };
  }
  if (["legal_review_pending", "legal_review_in_progress", "conflict_search_pending", "conflict_search_in_progress"].includes(status)) {
    return { step: 3, label: "Идёт проверка", action: "Посмотреть ход проверки" };
  }
  if (RESULT_STATUSES.has(status) || ["legal_review_done", "conflict_search_done", "memo_generation"].includes(status)) {
    return { step: 4, label: status === "submitted" ? "Заявка подана" : "Результат готов", action: "Посмотреть результат" };
  }
  return { step: 1, label: "Черновик", action: "Открыть заявку" };
}

function ApplicationCard({ application }: { application: Application }) {
  const stage = stageFor(application.status);
  const updated = new Date(application.updatedAt).toLocaleDateString("ru-RU", {
    day: "numeric",
    month: "long",
    year: "numeric",
  });

  return (
    <Link href={`/applications/${application.id}`}>
      <article className="group cursor-pointer rounded-[1.6rem] border border-[#11113f]/10 bg-white p-6 shadow-[0_12px_40px_rgba(21,21,55,0.05)] transition-all hover:-translate-y-0.5 hover:border-[#0d9f9b]/45 hover:shadow-[0_18px_50px_rgba(21,21,55,0.09)]">
        <div className="flex flex-col gap-5 sm:flex-row sm:items-start sm:justify-between">
          <div className="min-w-0">
            <p className="text-xs font-bold uppercase tracking-[0.16em] text-[#0d9f9b]">
              Заявка №{application.id}
            </p>
            <h2 className="mt-2 truncate text-2xl font-semibold text-[#11113f]">
              {application.markName}
            </h2>
            <p className="mt-1 text-sm text-[#6d6d7d]">Обновлено {updated}</p>
          </div>
          <span className="inline-flex w-fit items-center gap-2 rounded-full bg-[#f0f8f7] px-3.5 py-2 text-sm font-semibold text-[#087c78]">
            {stage.step === 4 ? <CheckCircle2 className="h-4 w-4" /> : <CircleDot className="h-4 w-4" />}
            {stage.label}
          </span>
        </div>

        <div className="mt-6 grid grid-cols-4 gap-2" aria-label={`Шаг ${stage.step} из 4`}>
          {[1, 2, 3, 4].map((step) => (
            <span
              key={step}
              className={`h-1.5 rounded-full ${step <= stage.step ? "bg-[#0d9f9b]" : "bg-[#11113f]/10"}`}
            />
          ))}
        </div>
        <div className="mt-5 flex items-center justify-between text-sm">
          <span className="text-[#6d6d7d]">Шаг {stage.step} из 4</span>
          <span className="flex items-center gap-1.5 font-semibold text-[#11113f] group-hover:text-[#0d9f9b]">
            {stage.action} <ArrowRight className="h-4 w-4" />
          </span>
        </div>
      </article>
    </Link>
  );
}

export default function ClientDashboardPage() {
  const { user } = useAuth();
  const [, setLocation] = useLocation();
  const cases = useCases();
  const applications = cases.data?.applications ?? [];
  const name = user?.preferredName || user?.fullName?.split(" ")[0] || "";

  return (
    <div className="space-y-10">
      <section className="relative overflow-hidden rounded-[2rem] bg-[#11113f] px-6 py-10 text-white sm:px-10 lg:px-14 lg:py-14">
        <div className="absolute -right-24 -top-24 h-72 w-72 rounded-full border border-[#2dbab5]/35" />
        <div className="absolute -bottom-40 right-24 h-80 w-80 rounded-full border border-white/10" />
        <div className="relative max-w-3xl">
          <p className="text-sm font-bold uppercase tracking-[0.16em] text-[#43c7c2]">
            Личный кабинет
          </p>
          <h1 className="mt-4 text-4xl font-semibold leading-tight sm:text-5xl lg:text-6xl">
            {name ? `${name}, защитим ваш бренд` : "Защитим ваш бренд"}
          </h1>
          <p className="mt-5 max-w-2xl text-base leading-relaxed text-white/70 sm:text-lg">
            Опишите товарный знак и загрузите документы. Мы подскажем классы МКТУ,
            проверим риски и соберём всё необходимое для подачи.
          </p>
          <Button
            className="mt-8 h-13 rounded-full bg-[#12aaa5] px-7 text-base text-white hover:bg-[#0d918d]"
            onClick={() => setLocation("/start")}
          >
            <Plus className="h-5 w-5" /> Начать проверку
          </Button>
        </div>
      </section>

      <section className="grid gap-4 sm:grid-cols-3">
        {[
          { icon: FileSearch, title: "Загрузите документы", text: "Реквизиты из выписки заполнятся автоматически" },
          { icon: Sparkles, title: "Получите проверку", text: "Классы и опасные совпадения — простым языком" },
          { icon: ShieldCheck, title: "Подготовьтесь к подаче", text: "Увидите, что заполнить и сколько оплатить" },
        ].map((item) => (
          <div key={item.title} className="rounded-[1.35rem] border border-[#11113f]/10 bg-white p-5">
            <item.icon className="h-6 w-6 text-[#0d9f9b]" />
            <h2 className="mt-4 font-semibold text-[#11113f]">{item.title}</h2>
            <p className="mt-1.5 text-sm leading-relaxed text-[#6d6d7d]">{item.text}</p>
          </div>
        ))}
      </section>

      <section>
        <div className="mb-5 flex items-end justify-between gap-4">
          <div>
            <p className="text-sm font-bold uppercase tracking-[0.14em] text-[#0d9f9b]">Ваши проекты</p>
            <h2 className="mt-2 text-3xl font-semibold text-[#11113f]">Мои заявки</h2>
          </div>
          {applications.length > 0 && (
            <Button variant="outline" className="hidden rounded-full sm:flex" onClick={() => setLocation("/start")}>
              <Plus className="h-4 w-4" /> Новая заявка
            </Button>
          )}
        </div>

        {cases.isLoading ? (
          <div className="flex min-h-48 items-center justify-center text-[#6d6d7d]">
            <Loader2 className="mr-2 h-5 w-5 animate-spin" /> Загружаем заявки…
          </div>
        ) : cases.error ? (
          <div className="rounded-[1.4rem] border border-red-200 bg-red-50 p-6 text-red-800">
            <p className="font-semibold">Не удалось загрузить заявки</p>
            <p className="mt-1 text-sm">{cases.error}</p>
            <Button variant="outline" className="mt-4 rounded-full" onClick={cases.reload}>Повторить</Button>
          </div>
        ) : applications.length === 0 ? (
          <div className="rounded-[1.6rem] border-2 border-dashed border-[#0d9f9b]/30 bg-white/70 px-6 py-14 text-center">
            <span className="mx-auto flex h-14 w-14 items-center justify-center rounded-full bg-[#e8f7f6] text-[#0d9f9b]">
              <Sparkles className="h-6 w-6" />
            </span>
            <h3 className="mt-5 text-2xl font-semibold">Заявок пока нет</h3>
            <p className="mx-auto mt-2 max-w-lg text-[#6d6d7d]">
              Начните с названия бренда и короткого описания бизнеса. Черновик можно дополнить позже.
            </p>
            <Button className="mt-6 rounded-full bg-[#0d9f9b] px-6 hover:bg-[#078984]" onClick={() => setLocation("/start")}>
              Проверить первый знак <ArrowRight className="h-4 w-4" />
            </Button>
          </div>
        ) : (
          <div className="grid gap-5 lg:grid-cols-2">
            {applications.map((application) => (
              <ApplicationCard key={application.id} application={application} />
            ))}
          </div>
        )}
      </section>
    </div>
  );
}
