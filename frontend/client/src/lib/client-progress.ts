import type { Application } from "@shared/schema";

const STAGES: Record<string, { step: number; label: string; action: string; section: string }> = {
  draft: { step: 1, label: "Данные о знаке", action: "Продолжить заполнение", section: "review" },
  classes: { step: 1, label: "Подбор товаров и услуг", action: "Проверить перечень", section: "review" },
  queued: { step: 2, label: "Проверка в очереди", action: "Посмотреть ход проверки", section: "analysis" },
  analyzing: { step: 2, label: "Идёт проверка", action: "Посмотреть ход проверки", section: "analysis" },
  failed: { step: 2, label: "Проверка прервана", action: "Посмотреть причину и повторить", section: "analysis" },
  incomplete: { step: 2, label: "Нужна дополнительная проверка", action: "Посмотреть результаты и ограничения", section: "analysis" },
  result: { step: 2, label: "Предварительный результат", action: "Посмотреть результат", section: "analysis" },
  documents: { step: 3, label: "Подготовка документов", action: "Проверить комплект", section: "documents" },
  submitted: { step: 3, label: "Заявка подана", action: "Открыть документы", section: "documents" },
  closed: { step: 3, label: "Дело закрыто", action: "Посмотреть документы", section: "documents" },
};

export function stageFor(application: Application) {
  const state = application.clientProgressState;
  if (state && STAGES[state]) return STAGES[state];
  if (application.status === "closed" || application.status === "submitted") return STAGES[application.status];
  return STAGES.draft;
}
