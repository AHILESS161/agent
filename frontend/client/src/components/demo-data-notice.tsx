import { FlaskConical } from "lucide-react";

/**
 * Пометка вкладки, данные которой пока демонстрационные.
 *
 * Нужна, чтобы демо-данные нельзя было принять за результат работы
 * системы: часть экранов уже читает БД, часть — ещё нет.
 */
export function DemoDataNotice() {
  return (
    <div
      className="mb-3 flex items-start gap-2 rounded-md border border-dashed border-border bg-muted/40 px-3 py-2"
      data-testid="demo-data-notice"
    >
      <FlaskConical className="w-4 h-4 shrink-0 mt-0.5 text-muted-foreground" />
      <p className="text-xs text-muted-foreground">
        <span className="font-medium text-foreground">Демонстрационные данные.</span>{" "}
        Этот раздел ещё не подключён к базе данных и показывает пример
        оформления. Реальные данные дела — на вкладках «Исходные документы»
        и «Сверка полей».
      </p>
    </div>
  );
}
