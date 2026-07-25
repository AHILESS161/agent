import { useEffect, useState } from "react";
import { api } from "./api";

/**
 * Число непрочитанных уведомлений.
 *
 * Сбой запроса намеренно не показывается пользователю: счётчик
 * второстепенен и не должен ломать навигацию.
 */
export function useUnreadCount(): number {
  const [count, setCount] = useState(0);

  useEffect(() => {
    let cancelled = false;
    api
      .get<{ unread_count?: number; count?: number }>("/notifications/unread-count")
      .then((data) => {
        if (!cancelled) setCount(data.unread_count ?? data.count ?? 0);
      })
      .catch(() => {
        if (!cancelled) setCount(0);
      });
    return () => {
      cancelled = true;
    };
  }, []);

  return count;
}
