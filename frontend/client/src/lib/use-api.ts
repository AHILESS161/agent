/**
 * Универсальный хук запроса к API.
 *
 * Даёт всем экранам одинаковое поведение: состояние загрузки, текст
 * ошибки и повтор. Отдельно обрабатывается 404: для многих разделов
 * «данных ещё нет» — это нормальное состояние, а не ошибка.
 */

import { useCallback, useEffect, useState } from "react";
import { api, ApiError } from "./api";

export interface ApiState<T> {
  data: T | null;
  isLoading: boolean;
  error: string | null;
  /** Ресурс не создан: анализ не запускался, документов нет и т. п. */
  isEmpty: boolean;
  reload: () => void;
}

interface Options {
  /** 404 трактуется как «пусто», а не как ошибка. */
  treat404AsEmpty?: boolean;
  /** Запрос выполняется методом POST (например, проверка полноты). */
  method?: "GET" | "POST";
  /** Не выполнять запрос, пока условие не выполнено. */
  enabled?: boolean;
}

export function useApi<T>(path: string | null, options: Options = {}): ApiState<T> {
  const { treat404AsEmpty = true, method = "GET", enabled = true } = options;

  const [data, setData] = useState<T | null>(null);
  const [isLoading, setIsLoading] = useState(enabled);
  const [error, setError] = useState<string | null>(null);
  const [isEmpty, setIsEmpty] = useState(false);
  const [tick, setTick] = useState(0);

  const reload = useCallback(() => setTick((t) => t + 1), []);

  useEffect(() => {
    if (!path || !enabled) {
      setIsLoading(false);
      return;
    }
    let cancelled = false;
    setIsLoading(true);
    setError(null);
    setIsEmpty(false);

    const request = method === "POST" ? api.post<T>(path) : api.get<T>(path);

    request
      .then((result) => {
        if (!cancelled) setData(result);
      })
      .catch((e) => {
        if (cancelled) return;
        if (treat404AsEmpty && e instanceof ApiError && e.status === 404) {
          setIsEmpty(true);
          setData(null);
          return;
        }
        setError(e instanceof ApiError ? e.message : "Не удалось загрузить данные");
      })
      .finally(() => {
        if (!cancelled) setIsLoading(false);
      });

    return () => {
      cancelled = true;
    };
  }, [path, method, treat404AsEmpty, enabled, tick]);

  return { data, isLoading, error, isEmpty, reload };
}

// ---------------------------------------------------------------------------
// Типы ответов backend
// ---------------------------------------------------------------------------

export interface Paginated<T> {
  items: T[];
  total: number;
  page: number;
  page_size: number;
  total_pages: number;
}

export interface ClassSuggestionDto {
  id: number;
  application_id: number;
  class_number: number;
  class_description: string | null;
  rationale: string | null;
  confidence: number | null;
  category: string | null;
  risks_if_omitted: string | null;
  risks_if_included: string | null;
  approved: boolean | null;
}

export interface ClassesDto {
  application_id: number;
  suggestions: ClassSuggestionDto[];
}

export interface CompletenessDto {
  is_complete: boolean;
  blocking_issues: { field: string; message: string; severity?: string }[];
  non_blocking_issues: { field: string; message: string; severity?: string }[];
  stage: string;
  recommended_message: string | null;
}

export interface StatusDto {
  application_id: number;
  status: string;
  allowed_transitions: string[];
  submission: Record<string, unknown> | null;
  status_events: {
    id?: number;
    status?: string;
    event_type?: string;
    description?: string;
    created_at?: string;
  }[];
}

export interface DocumentPackagesDto {
  application_id: number;
  packages: {
    id: number;
    template_id?: number;
    status: string;
    file_path?: string | null;
    approved_by?: number | null;
    created_at?: string;
  }[];
}

export interface ConflictsDto {
  application_id: number;
  job?: { id: number; status: string; provider?: string; total_results?: number };
  results?: {
    id: number;
    external_id?: string;
    mark_text?: string;
    owner?: string;
    classes?: number[];
    similarity_score?: number;
    decision?: string | null;
    status?: string;
  }[];
}

export interface LegalReviewDto {
  id: number;
  application_id: number;
  review_type: string;
  absolute_grounds_summary: string | null;
  relative_grounds_summary: string | null;
  risk_level: string | null;
  confidence_score: number | null;
  reviewer_decision: string | null;
  findings?: {
    id: number;
    finding_type: string;
    ground_article: string | null;
    description: string;
    severity: string;
    confidence: number | null;
    recommendation: string | null;
  }[];
}

export interface AuditEntryDto {
  id: number;
  user_id: number | null;
  application_id: number | null;
  action: string;
  entity_type: string | null;
  entity_id: string | null;
  ip_address: string | null;
  created_at: string;
}

export interface NotificationDto {
  id: number;
  type: string;
  title: string;
  message: string;
  is_read: boolean;
  application_id: number | null;
  created_at: string;
}

export interface NotificationsDto {
  items: NotificationDto[];
  unread_count: number;
  total: number;
}

export interface UserDto {
  id: number;
  email: string;
  full_name: string | null;
  role: string;
  is_active: boolean;
  created_at: string;
}

export interface AdminStatsDto {
  users: { total: number; active: number; inactive: number };
  clients: { total: number };
  applications: {
    total: number;
    draft: number;
    submitted: number;
    in_progress: number;
  };
  legal_reviews: { total: number };
  conflict_results: { total: number };
  class_suggestions: { total: number };
  document_packages: { total: number };
  submissions: { total: number };
  agent_runs?: Record<string, number>;
}
