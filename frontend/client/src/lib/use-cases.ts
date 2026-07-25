/**
 * Хуки доступа к делам и клиентам через REST API.
 *
 * Ответы бэкенда приходят в snake_case и нормализуются в типы
 * приложения (camelCase), объявленные в @shared/schema.
 */

import { useCallback, useEffect, useState } from "react";
import { api, ApiError } from "./api";
import type { Application, Client, ApplicationStatus, MarkType } from "@shared/schema";

// --- DTO бэкенда --------------------------------------------------------

interface ApplicationDto {
  id: number;
  client_id: number;
  assigned_lawyer_id: number | null;
  assigned_manager_id: number | null;
  status: ApplicationStatus;
  mark_type: MarkType | null;
  mark_name: string | null;
  mark_text?: string | null;
  transliteration?: string | null;
  translation?: string | null;
  description_of_mark?: string | null;
  business_description?: string | null;
  goods_services_raw?: string | null;
  territory?: string | null;
  priority_claim?: string | null;
  notes?: string | null;
  created_at: string;
  updated_at: string;
}

interface ClientDto {
  id: number;
  type: Client["type"];
  full_name_or_company_name: string;
  short_name: string | null;
  contact_person: string | null;
  email: string | null;
  phone: string | null;
  address: string | null;
  country: string | null;
  inn: string | null;
  ogrn_or_ogrnip: string | null;
  created_at: string;
  updated_at: string;
}

interface Paginated<T> {
  items: T[];
  total: number;
  page: number;
  page_size: number;
  total_pages: number;
}

// --- Нормализация -------------------------------------------------------

function toApplication(dto: ApplicationDto): Application {
  return {
    id: dto.id,
    clientId: dto.client_id,
    status: dto.status,
    // mark_type на сервере необязателен, в интерфейсе нужен всегда.
    markType: (dto.mark_type ?? "other") as MarkType,
    markName: dto.mark_name ?? `Заявка №${dto.id}`,
    markText: dto.mark_text ?? "",
    colorsClaimed: "",
    transliteration: dto.transliteration ?? "",
    translation: dto.translation ?? "",
    descriptionOfMark: dto.description_of_mark ?? "",
    businessDescription: dto.business_description ?? "",
    goodsServicesRaw: dto.goods_services_raw ?? "",
    territory: dto.territory ?? "",
    priorityClaim: dto.priority_claim ?? "",
    notes: dto.notes ?? "",
    assigneeId: dto.assigned_lawyer_id ?? dto.assigned_manager_id ?? undefined,
    createdAt: dto.created_at,
    updatedAt: dto.updated_at,
  };
}

function toClient(dto: ClientDto): Client {
  return {
    id: dto.id,
    type: dto.type,
    fullNameOrCompanyName: dto.full_name_or_company_name,
    shortName: dto.short_name ?? dto.full_name_or_company_name,
    contactPerson: dto.contact_person ?? "",
    email: dto.email ?? "",
    phone: dto.phone ?? "",
    address: dto.address ?? "",
    inn: dto.inn ?? "",
    ogrnOrOgrnip: dto.ogrn_or_ogrnip ?? "",
    createdAt: dto.created_at,
  };
}

// --- Состояние запроса --------------------------------------------------

export interface AsyncState<T> {
  data: T | null;
  isLoading: boolean;
  error: string | null;
  reload: () => void;
}

function messageOf(error: unknown, fallback: string): string {
  return error instanceof ApiError ? error.message : fallback;
}

// --- Хуки ---------------------------------------------------------------

export interface CasesData {
  applications: Application[];
  clientsById: Record<number, Client>;
}

/** Список дел вместе со справочником клиентов. */
export function useCases(pageSize = 100): AsyncState<CasesData> {
  const [data, setData] = useState<CasesData | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [tick, setTick] = useState(0);

  const reload = useCallback(() => setTick((t) => t + 1), []);

  useEffect(() => {
    let cancelled = false;
    setIsLoading(true);
    setError(null);

    Promise.all([
      api.get<Paginated<ApplicationDto>>(`/applications?page=1&page_size=${pageSize}`),
      api.get<Paginated<ClientDto>>(`/clients?page=1&page_size=${pageSize}`),
    ])
      .then(([apps, clients]) => {
        if (cancelled) return;
        const clientsById: Record<number, Client> = {};
        for (const dto of clients.items) clientsById[dto.id] = toClient(dto);
        setData({ applications: apps.items.map(toApplication), clientsById });
      })
      .catch((e) => {
        if (!cancelled) setError(messageOf(e, "Не удалось загрузить список дел"));
      })
      .finally(() => {
        if (!cancelled) setIsLoading(false);
      });

    return () => {
      cancelled = true;
    };
  }, [pageSize, tick]);

  return { data, isLoading, error, reload };
}

export interface CaseData {
  application: Application;
  client: Client | null;
}

/** Одно дело вместе с его клиентом. */
export function useCase(applicationId: number): AsyncState<CaseData> {
  const [data, setData] = useState<CaseData | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [tick, setTick] = useState(0);

  const reload = useCallback(() => setTick((t) => t + 1), []);

  useEffect(() => {
    if (!applicationId) {
      setIsLoading(false);
      setError("Некорректный номер дела");
      return;
    }
    let cancelled = false;
    setIsLoading(true);
    setError(null);

    api
      .get<ApplicationDto>(`/applications/${applicationId}`)
      .then(async (dto) => {
        const application = toApplication(dto);
        let client: Client | null = null;
        try {
          client = toClient(await api.get<ClientDto>(`/clients/${dto.client_id}`));
        } catch {
          // Дело показываем и без карточки клиента — это не критично.
        }
        if (!cancelled) setData({ application, client });
      })
      .catch((e) => {
        if (!cancelled) setError(messageOf(e, "Не удалось загрузить дело"));
      })
      .finally(() => {
        if (!cancelled) setIsLoading(false);
      });

    return () => {
      cancelled = true;
    };
  }, [applicationId, tick]);

  return { data, isLoading, error, reload };
}
