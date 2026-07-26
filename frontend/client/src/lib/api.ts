/**
 * Клиент REST API.
 *
 * Запросы идут на относительный путь /api/v1: в разработке их
 * проксирует Vite на FastAPI, в production их отдаёт тот же origin.
 * Адрес бэкенда нигде в исходном коде не зашит — это позволяет
 * работать и локально, и через внешний туннель.
 */

const TOKEN_STORAGE_KEY = "tm_access_token";

export class ApiError extends Error {
  constructor(
    public readonly status: number,
    message: string,
    public readonly detail?: unknown,
  ) {
    super(message);
    this.name = "ApiError";
  }

  /** Сессия истекла или токен недействителен. */
  get isAuthError(): boolean {
    return this.status === 401;
  }

  /** Недостаточно прав. */
  get isForbidden(): boolean {
    return this.status === 403;
  }
}

export function getToken(): string | null {
  return localStorage.getItem(TOKEN_STORAGE_KEY);
}

export function setToken(token: string): void {
  localStorage.setItem(TOKEN_STORAGE_KEY, token);
}

export function clearToken(): void {
  localStorage.removeItem(TOKEN_STORAGE_KEY);
}

/** Вызывается при 401, чтобы приложение вернуло пользователя ко входу. */
let onUnauthorized: (() => void) | null = null;

export function setUnauthorizedHandler(handler: () => void): void {
  onUnauthorized = handler;
}

function authHeaders(): Record<string, string> {
  const token = getToken();
  return token ? { Authorization: `Bearer ${token}` } : {};
}

async function toApiError(response: Response): Promise<ApiError> {
  let detail: unknown;
  let message = `Ошибка ${response.status}`;
  try {
    const body = await response.json();
    detail = body?.detail ?? body;
    if (typeof detail === "string") {
      message = detail;
    } else if (Array.isArray(detail) && detail[0]?.msg) {
      // Ошибка валидации FastAPI.
      message = detail.map((d: any) => d.msg).join("; ");
    }
  } catch {
    // Тело не JSON — оставляем сообщение по коду статуса.
  }

  if (response.status === 401) message = "Сессия истекла. Войдите заново.";
  if (response.status === 403) message = "Недостаточно прав для этого действия.";
  if (response.status === 404 && typeof detail !== "string") message = "Не найдено.";
  if (response.status >= 500) {
    // Внутренние подробности пользователю не показываем.
    message = "Внутренняя ошибка сервера. Попробуйте позже.";
  }

  return new ApiError(response.status, message, detail);
}

async function request<T>(
  method: string,
  path: string,
  body?: unknown,
  options: { raw?: boolean } = {},
): Promise<T> {
  const isFormData = body instanceof FormData;

  const response = await fetch(`/api/v1${path}`, {
    method,
    headers: {
      ...authHeaders(),
      ...(body !== undefined && !isFormData
        ? { "Content-Type": "application/json" }
        : {}),
    },
    body: isFormData ? body : body !== undefined ? JSON.stringify(body) : undefined,
  });

  if (!response.ok) {
    const error = await toApiError(response);
    if (error.isAuthError) {
      clearToken();
      onUnauthorized?.();
    }
    throw error;
  }

  if (options.raw) return response as unknown as T;
  if (response.status === 204) return undefined as T;
  return (await response.json()) as T;
}

export const api = {
  get: <T>(path: string) => request<T>("GET", path),
  post: <T>(path: string, body?: unknown) => request<T>("POST", path, body),
  put: <T>(path: string, body?: unknown) => request<T>("PUT", path, body),
  delete: <T>(path: string) => request<T>("DELETE", path),
  /** Загрузка файла multipart/form-data. */
  upload: <T>(path: string, file: File) => {
    const form = new FormData();
    form.append("file", file);
    return request<T>("POST", path, form);
  },
  /** Скачивание файла с авторизацией (прямая ссылка не сработает). */
  download: async (path: string, filename: string): Promise<void> => {
    const response = await fetch(`/api/v1${path}`, { headers: authHeaders() });
    if (!response.ok) throw await toApiError(response);

    const blob = await response.blob();
    const url = URL.createObjectURL(blob);
    const link = document.createElement("a");
    link.href = url;
    link.download = filename;
    document.body.appendChild(link);
    link.click();
    link.remove();
    URL.revokeObjectURL(url);
  },
};

// ---------------------------------------------------------------------------
// Типы ответов, используемые новыми экранами
// ---------------------------------------------------------------------------

export interface SourceDocumentDto {
  id: number;
  application_id: number | null;
  original_filename: string;
  file_size: number;
  sha256: string;
  detected_mime: string | null;
  document_kind: string;
  kind_confidence: number | null;
  kind_requires_confirmation: boolean;
  processing_status: string;
  extraction_method: string | null;
  page_count: number | null;
  char_count: number | null;
  error_message: string | null;
  created_at: string | null;
  warning?: string;
}

export interface FieldCandidateDto {
  id: number;
  raw_value: string;
  normalized_value: string | null;
  pattern_id: string | null;
  confidence: number | null;
  page_number: number | null;
  validation_passed: boolean | null;
  is_selected: boolean;
}

export interface ReconciliationItemDto {
  extracted_field_id: number | null;
  label: string;
  registry_field: string | null;
  case_field: string;
  application_field: string | null;
  /** Человекочитаемое имя поля бланка с кодом INID. */
  application_field_label?: string | null;
  status: string;
  registry_value: string | null;
  registry_raw_value: string | null;
  case_value: string | null;
  default_value: string | null;
  confidence: number | null;
  page_number: number | null;
  pattern_id: string | null;
  extraction_method: string | null;
  source_snippet: string;
  required_for_application: boolean;
  critical: boolean;
  is_sensitive: boolean;
  normalization_changed: boolean;
  validation_error: string | null;
  note: string | null;
  candidates: FieldCandidateDto[];
  available_actions: string[];
  /** Поле заведено специалистом, а не извлечено из документа. */
  is_custom?: boolean;
  blocks_document_generation: boolean;
}

export interface ReconciliationDto {
  application_id: number;
  summary: {
    mapping_version: number;
    application_schema_version: string;
    total: number;
    by_status: Record<string, number>;
    requires_attention: number;
    blocking_document_generation: string[];
    can_generate_draft: boolean;
    not_sourced_from_registry: { field: string; reason: string }[];
  };
  items: ReconciliationItemDto[];
  disclaimer: string;
}

export const DOCUMENT_KIND_LABELS: Record<string, string> = {
  trademark_application: "Заявка на товарный знак",
  egrul_extract: "Выписка ЕГРЮЛ",
  egrip_extract: "Выписка ЕГРИП",
  unknown_registry_extract: "Реестровая справка (тип не определён)",
  power_of_attorney: "Доверенность",
  mark_image: "Изображение обозначения",
  other: "Иной документ",
  unknown: "Тип не определён",
};

export const FIELD_STATUS_LABELS: Record<string, string> = {
  matched: "Извлечено",
  missing: "Не найдено",
  conflict: "Конфликт",
  needs_review: "Требует проверки",
  confirmed: "Подтверждено",
  rejected: "Отклонено",
  left_empty: "Оставлено пустым",
};

export const PROCESSING_STATUS_LABELS: Record<string, string> = {
  uploaded: "Загружен",
  extracting: "Обработка",
  extracted: "Текст извлечён",
  failed: "Ошибка обработки",
  rejected: "Отклонён",
};
