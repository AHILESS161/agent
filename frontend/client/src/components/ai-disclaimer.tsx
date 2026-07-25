import { AlertTriangle, Info } from "lucide-react";

/**
 * Предупреждение об ограничениях автоматического анализа.
 *
 * Показывается везде, где пользователь видит результаты автоматической
 * обработки: извлечённые реквизиты, оценку рисков, черновики документов.
 */
export function AiDisclaimer({ compact = false }: { compact?: boolean }) {
  if (compact) {
    return (
      <p className="flex items-start gap-1.5 text-[11px] leading-relaxed text-muted-foreground">
        <Info className="w-3.5 h-3.5 shrink-0 mt-px" />
        Результаты сформированы автоматически и носят предварительный
        характер. Требуется проверка специалистом.
      </p>
    );
  }

  return (
    <div
      className="flex items-start gap-2 rounded-md border border-amber-500/40 bg-amber-500/10 px-3 py-2"
      data-testid="ai-disclaimer"
    >
      <AlertTriangle className="w-4 h-4 shrink-0 mt-0.5 text-amber-600 dark:text-amber-500" />
      <p className="text-xs leading-relaxed text-foreground">
        Результаты сформированы с применением AI и носят предварительный
        информационный характер. Они требуют проверки специалистом.
      </p>
    </div>
  );
}

/**
 * Отметка режима работы поиска/интеграций.
 * Demo-режим должен быть явно виден, а не выглядеть как реальные данные.
 */
export function DemoModeBadge({ label = "Демо-режим" }: { label?: string }) {
  return (
    <span
      className="inline-flex items-center rounded border border-amber-500/50 bg-amber-500/10 px-1.5 py-0.5 text-[10px] font-medium text-amber-700 dark:text-amber-500"
      data-testid="demo-badge"
    >
      {label}
    </span>
  );
}
