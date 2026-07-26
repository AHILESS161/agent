import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { AlertCircle, Inbox, Loader2, RefreshCw } from "lucide-react";
import type { ReactNode } from "react";

/** Единое состояние загрузки для всех разделов. */
export function LoadingState({ label = "Загрузка…" }: { label?: string }) {
  return (
    <div
      className="flex items-center justify-center gap-2 py-12 text-muted-foreground"
      data-testid="loading-state"
    >
      <Loader2 className="w-4 h-4 animate-spin" />
      <span className="text-sm">{label}</span>
    </div>
  );
}

/** Ошибка запроса с возможностью повторить. */
export function ErrorState({
  message,
  onRetry,
}: {
  message: string;
  onRetry?: () => void;
}) {
  return (
    <div
      className="flex items-start gap-2 rounded-md border border-destructive/40 bg-destructive/10 px-3 py-2"
      data-testid="error-state"
    >
      <AlertCircle className="w-4 h-4 shrink-0 mt-0.5 text-destructive" />
      <p className="flex-1 text-xs">{message}</p>
      {onRetry && (
        <Button variant="ghost" size="sm" onClick={onRetry}>
          <RefreshCw className="w-3.5 h-3.5 mr-1.5" />
          Повторить
        </Button>
      )}
    </div>
  );
}

/**
 * Пустое состояние.
 *
 * Отличается от ошибки: данных ещё нет, потому что соответствующий шаг
 * не выполнялся. Пользователю показывается, что именно нужно сделать.
 */
export function EmptyState({
  title,
  hint,
  action,
}: {
  title: string;
  hint?: string;
  action?: ReactNode;
}) {
  return (
    <Card className="border-dashed" data-testid="empty-state">
      <CardContent className="flex flex-col items-center justify-center py-10 text-center">
        <Inbox className="w-8 h-8 text-muted-foreground mb-3" />
        <p className="text-sm font-medium">{title}</p>
        {hint && (
          <p className="text-xs text-muted-foreground mt-1 max-w-sm">{hint}</p>
        )}
        {action && <div className="mt-3">{action}</div>}
      </CardContent>
    </Card>
  );
}

/**
 * Обёртка, сводящая три состояния к одному месту.
 * Избавляет каждый раздел от повторения одной и той же логики.
 */
export function AsyncSection<T>({
  state,
  emptyTitle,
  emptyHint,
  emptyAction,
  loadingLabel,
  children,
}: {
  state: {
    data: T | null;
    isLoading: boolean;
    error: string | null;
    isEmpty: boolean;
    reload: () => void;
  };
  emptyTitle: string;
  emptyHint?: string;
  emptyAction?: ReactNode;
  loadingLabel?: string;
  children: (data: T) => ReactNode;
}) {
  if (state.isLoading) return <LoadingState label={loadingLabel} />;
  if (state.error) return <ErrorState message={state.error} onRetry={state.reload} />;
  if (state.isEmpty || !state.data)
    return <EmptyState title={emptyTitle} hint={emptyHint} action={emptyAction} />;
  return <>{children(state.data)}</>;
}
