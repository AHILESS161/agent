import { useState } from "react";
import { Link, useLocation } from "wouter";
import {
  ArrowRight,
  CheckCircle2,
  CircleDot,
  Loader2,
  Sparkles,
  Trash2,
} from "lucide-react";
import { Button } from "@/components/ui/button";
import { useToast } from "@/hooks/use-toast";
import { api, ApiError } from "@/lib/api";
import { useCases } from "@/lib/use-cases";
import type { Application } from "@shared/schema";

import { stageFor } from "@/lib/client-progress";

function ApplicationCard({
  application,
  onDeleted,
}: {
  application: Application;
  onDeleted: () => void;
}) {
  const { toast } = useToast();
  const [isDeleting, setIsDeleting] = useState(false);
  const stage = stageFor(application);
  const updated = new Date(application.updatedAt).toLocaleDateString("ru-RU", {
    day: "numeric",
    month: "long",
    year: "numeric",
  });
  const canDelete = !["submitted", "closed"].includes(application.status);

  const remove = async () => {
    const confirmed = window.confirm(
      `Удалить заявку «${application.markName}»?\n\n` +
        "Вместе с ней будут удалены документы и результаты проверки. " +
        "Отменить это действие будет нельзя.",
    );
    if (!confirmed) return;

    setIsDeleting(true);
    try {
      await api.delete(`/applications/${application.id}`);
      toast({ title: `Заявка «${application.markName}» удалена` });
      onDeleted();
    } catch (error) {
      toast({
        title: "Не удалось удалить заявку",
        description: error instanceof ApiError ? error.message : "Попробуйте ещё раз",
        variant: "destructive",
      });
    } finally {
      setIsDeleting(false);
    }
  };

  return (
    <Link href={`/applications/${application.id}?step=${stage.section}`}>
      <article className="group cursor-pointer rounded-[1.6rem] border border-[#38322e]/10 bg-white p-6 shadow-[0_12px_40px_rgba(21,21,55,0.05)] transition-all hover:-translate-y-0.5 hover:border-[#9b8258]/45 hover:shadow-[0_18px_50px_rgba(21,21,55,0.09)]">
        <div className="flex flex-col gap-5 sm:flex-row sm:items-start sm:justify-between">
          <div className="min-w-0">
            <p className="text-xs font-bold uppercase tracking-[0.16em] text-[#9b8258]">
              Заявка №{application.id}
            </p>
            <h2 className="mt-2 truncate text-2xl font-semibold text-[#38322e]">
              {application.markName}
            </h2>
            <p className="mt-1 text-sm text-[#746e66]">Обновлено {updated}</p>
          </div>
          <div className="flex flex-wrap items-center justify-end gap-2">
            <span className="inline-flex w-fit items-center gap-2 rounded-full bg-[#f4f1eb] px-3.5 py-2 text-sm font-semibold text-[#786341]">
              {["submitted", "closed"].includes(application.status) ? <CheckCircle2 className="h-4 w-4" /> : <CircleDot className="h-4 w-4" />}
              {stage.label}
            </span>
            {canDelete && (
              <Button
                type="button"
                variant="ghost"
                size="sm"
                className="rounded-full px-3 text-[#8a5260] hover:bg-red-50 hover:text-red-700"
                disabled={isDeleting}
                onClick={(event) => {
                  event.preventDefault();
                  event.stopPropagation();
                  void remove();
                }}
                aria-label={`Удалить заявку «${application.markName}»`}
              >
                {isDeleting ? <Loader2 className="h-4 w-4 animate-spin" /> : <Trash2 className="h-4 w-4" />}
                Удалить
              </Button>
            )}
          </div>
        </div>

        <div className="mt-6 grid grid-cols-3 gap-2" aria-label={`Этап ${stage.step} из 3`}>
          {[1, 2, 3].map((step) => (
            <span
              key={step}
              className={`h-1.5 rounded-full ${step <= stage.step ? "bg-[#9b8258]" : "bg-[#38322e]/10"}`}
            />
          ))}
        </div>
        <div className="mt-5 flex items-center justify-between text-sm">
          <span className="text-[#746e66]">Этап {stage.step} из 3</span>
          <span className="flex items-center gap-1.5 font-semibold text-[#38322e] group-hover:text-[#9b8258]">
            {stage.action} <ArrowRight className="h-4 w-4" />
          </span>
        </div>
      </article>
    </Link>
  );
}

export default function ClientDashboardPage() {
  const [, setLocation] = useLocation();
  const cases = useCases();
  const applications = cases.data?.applications ?? [];

  return (
    <div className="space-y-10">
      <section>
        <div className="mb-8 flex flex-col gap-5 sm:flex-row sm:items-end sm:justify-between">
          <div>
            <p className="text-xs font-semibold uppercase tracking-[0.16em] text-[#9b8258]">Личный кабинет</p>
            <h1 className="registr-serif mt-3 text-5xl text-[#38322e] sm:text-6xl">Мои заявки</h1>
            <p className="mt-3 text-sm leading-6 text-[#746e66]">Проверки брендов, документы и текущий этап каждой заявки.</p>
          </div>
          <Button className="min-h-12 w-fit shrink-0 rounded-full px-6" onClick={() => setLocation("/start")}>Новая заявка<ArrowRight className="h-4 w-4" /></Button>
        </div>

        {cases.isLoading ? (
          <div className="flex min-h-48 items-center justify-center text-[#746e66]">
            <Loader2 className="mr-2 h-5 w-5 animate-spin" /> Загружаем заявки…
          </div>
        ) : cases.error ? (
          <div className="rounded-[1.4rem] border border-red-200 bg-red-50 p-6 text-red-800">
            <p className="font-semibold">Не удалось загрузить заявки</p>
            <p className="mt-1 text-sm">{cases.error}</p>
            <Button variant="outline" className="mt-4 rounded-full" onClick={cases.reload}>Повторить</Button>
          </div>
        ) : applications.length === 0 ? (
          <div className="rounded-[1.6rem] border-2 border-dashed border-[#9b8258]/30 bg-white/70 px-6 py-14 text-center">
            <span className="mx-auto flex h-14 w-14 items-center justify-center rounded-full bg-[#f0e9dc] text-[#9b8258]">
              <Sparkles className="h-6 w-6" />
            </span>
            <h3 className="mt-5 text-2xl font-semibold">Заявок пока нет</h3>
            <p className="mx-auto mt-2 max-w-lg text-[#746e66]">
              Начните с названия бренда и короткого описания бизнеса. Черновик можно дополнить позже.
            </p>
            <Button className="mt-5 min-h-12 rounded-full px-6" onClick={() => setLocation("/start")}>Создать первую заявку<ArrowRight className="h-4 w-4" /></Button>
          </div>
        ) : (
          <div className="grid gap-5 lg:grid-cols-2">
            {applications.map((application) => (
              <ApplicationCard
                key={application.id}
                application={application}
                onDeleted={cases.reload}
              />
            ))}
          </div>
        )}
      </section>
    </div>
  );
}
