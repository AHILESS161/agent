import { z } from "zod";

// ========== ENUMS ==========

export const ApplicationStatusEnum = z.enum([
  // Совпадает с ApplicationStatus на бэкенде (18 состояний).
  // Источник правды — машина состояний backend/app/services/state_machine.py.
  "draft",
  "info_requested",
  "info_received",
  "classification_pending",
  "classification_review",
  "classification_approved",
  "legal_review_pending",
  "legal_review_in_progress",
  "legal_review_done",
  "conflict_search_pending",
  "conflict_search_in_progress",
  "conflict_search_done",
  "memo_generation",
  "memo_approved",
  "document_generation",
  "document_approved",
  "submitted",
  "closed",
]);
export type ApplicationStatus = z.infer<typeof ApplicationStatusEnum>;

export const UserRoleEnum = z.enum(["admin", "lawyer", "manager", "client"]);
export type UserRole = z.infer<typeof UserRoleEnum>;

export const ClientTypeEnum = z.enum(["company", "individual", "sole_proprietor"]);
export type ClientType = z.infer<typeof ClientTypeEnum>;

export const MarkTypeEnum = z.enum(["word", "figurative", "combined", "3d", "sound", "color", "other"]);
export type MarkType = z.infer<typeof MarkTypeEnum>;

export const RiskLevelEnum = z.enum(["low", "medium", "high", "critical"]);
export type RiskLevel = z.infer<typeof RiskLevelEnum>;

export const ReviewDecisionEnum = z.enum(["approve", "reject", "modify"]);
export type ReviewDecision = z.infer<typeof ReviewDecisionEnum>;

// ========== TYPES ==========

export interface User {
  id: number;
  email: string;
  fullName: string;
  /** Как обращаться к человеку. */
  preferredName?: string | null;
  role: UserRole;
  isActive: boolean;
}

export interface Client {
  id: number;
  type: ClientType;
  fullNameOrCompanyName: string;
  shortName: string;
  contactPerson: string;
  email: string;
  phone: string;
  address: string;
  countryCode: string;
  inn: string;
  ogrnOrOgrnip: string;
  kpp: string;
  createdAt: string;
}

export interface Application {
  id: number;
  clientId: number;
  status: ApplicationStatus;
  /** Срочность в работе, не конвенционный приоритет заявки. */
  priority: CasePriority;
  markType: MarkType;
  markName: string;
  markText: string;
  markImageFileId: string;
  colorsClaimed: string;
  transliteration: string;
  translation: string;
  descriptionOfMark: string;
  businessDescription: string;
  goodsServicesRaw: string;
  territory: string;
  priorityClaim: string;
  filingMethod: "electronic" | "paper";
  requestPaperCertificate: boolean;
  representativeId?: number | null;
  signatoryName: string;
  signatoryPosition: string;
  signatureDate: string;
  notes: string;
  assigneeId?: number;
  createdAt: string;
  updatedAt: string;
}

export interface GoodsServicesItem {
  id: number;
  applicationId: number;
  rawText: string;
  normalizedText: string;
  proposedClass: number;
  approvedClass: number | null;
  source: string;
}

export interface NiceClassSuggestion {
  id: number;
  applicationId: number;
  classNumber: number;
  classDescription: string;
  rationale: string;
  confidence: number;
  category: "primary" | "secondary" | "borderline";
  risksIfOmitted: string;
  risksIfIncluded: string;
  approved: boolean | null;
}

export interface LegalReview {
  id: number;
  applicationId: number;
  reviewType: string;
  absoluteGroundsSummary: string;
  relativeGroundsSummary: string;
  riskLevel: RiskLevel;
  confidenceScore: number;
  reviewerDecision: ReviewDecision | null;
  overrideReason: string;
  createdAt: string;
}

export interface LegalFinding {
  id: number;
  legalReviewId: number;
  findingType: string;
  groundArticle: string;
  description: string;
  severity: RiskLevel;
  confidence: number;
  evidence: string;
  sourceReference: string;
  recommendation: string;
}

export interface ConflictSearchResult {
  id: number;
  applicationId: number;
  matchedMark: string;
  owner: string;
  classes: string;
  status: string;
  similarityScore: number;
  phoneticScore: number;
  conflictReason: string;
  reviewerDecision: ReviewDecision | null;
}

export interface RecommendationMemo {
  id: number;
  applicationId: number;
  summary: string;
  riskAssessment: string;
  recommendedAction: string;
  confidence: number;
}

export interface DocumentPackage {
  id: number;
  applicationId: number;
  generationStatus: string;
  approvedBy: number | null;
  approvedAt: string | null;
  createdAt: string;
}

export interface Notification {
  id: number;
  userId: number;
  applicationId: number;
  type: string;
  title: string;
  message: string;
  isRead: boolean;
  createdAt: string;
}

export interface AuditLog {
  id: number;
  userId: number;
  applicationId: number | null;
  action: string;
  entityType: string;
  createdAt: string;
}

export interface CompletenessCheck {
  field: string;
  label: string;
  present: boolean;
  severity: "blocking" | "non_blocking";
  reason: string;
  provider: string;
}

export interface StatusHistoryEntry {
  id: number;
  applicationId: number;
  fromStatus: ApplicationStatus | null;
  toStatus: ApplicationStatus;
  changedBy: string;
  comment: string;
  createdAt: string;
}

// ========== STATUS LABELS ==========

export const STATUS_LABELS: Record<ApplicationStatus, string> = {
  draft: "Черновик",
  info_requested: "Запрошены данные",
  info_received: "Данные получены",
  classification_pending: "Ожидает классификации",
  classification_review: "Проверка классов МКТУ",
  classification_approved: "Классы утверждены",
  legal_review_pending: "Ожидает правовой экспертизы",
  legal_review_in_progress: "Правовая экспертиза",
  legal_review_done: "Экспертиза завершена",
  conflict_search_pending: "Ожидает поиска конфликтов",
  conflict_search_in_progress: "Поиск конфликтов",
  conflict_search_done: "Поиск завершён",
  memo_generation: "Подготовка заключения",
  memo_approved: "Заключение утверждено",
  document_generation: "Формирование документов",
  document_approved: "Документы утверждены",
  submitted: "Подана",
  closed: "Закрыта",
};

export const STATUS_COLORS: Record<ApplicationStatus, string> = {
  draft: "bg-slate-100 text-slate-700 dark:bg-slate-800 dark:text-slate-300",
  info_requested: "bg-amber-100 text-amber-800 dark:bg-amber-900/30 dark:text-amber-400",
  info_received: "bg-blue-100 text-blue-800 dark:bg-blue-900/30 dark:text-blue-400",
  classification_pending: "bg-cyan-100 text-cyan-800 dark:bg-cyan-900/30 dark:text-cyan-400",
  classification_review: "bg-cyan-100 text-cyan-800 dark:bg-cyan-900/30 dark:text-cyan-400",
  classification_approved: "bg-teal-100 text-teal-800 dark:bg-teal-900/30 dark:text-teal-400",
  legal_review_pending: "bg-orange-100 text-orange-800 dark:bg-orange-900/30 dark:text-orange-400",
  legal_review_in_progress: "bg-violet-100 text-violet-800 dark:bg-violet-900/30 dark:text-violet-400",
  legal_review_done: "bg-teal-100 text-teal-800 dark:bg-teal-900/30 dark:text-teal-400",
  conflict_search_pending: "bg-indigo-100 text-indigo-800 dark:bg-indigo-900/30 dark:text-indigo-400",
  conflict_search_in_progress: "bg-indigo-100 text-indigo-800 dark:bg-indigo-900/30 dark:text-indigo-400",
  conflict_search_done: "bg-teal-100 text-teal-800 dark:bg-teal-900/30 dark:text-teal-400",
  memo_generation: "bg-blue-100 text-blue-800 dark:bg-blue-900/30 dark:text-blue-400",
  memo_approved: "bg-emerald-100 text-emerald-800 dark:bg-emerald-900/30 dark:text-emerald-400",
  document_generation: "bg-blue-100 text-blue-800 dark:bg-blue-900/30 dark:text-blue-400",
  document_approved: "bg-emerald-100 text-emerald-800 dark:bg-emerald-900/30 dark:text-emerald-400",
  submitted: "bg-green-100 text-green-800 dark:bg-green-900/30 dark:text-green-400",
  closed: "bg-gray-100 text-gray-600 dark:bg-gray-800 dark:text-gray-400",
};

export const ROLE_LABELS: Record<UserRole, string> = {
  admin: "Администратор",
  lawyer: "Юрист",
  manager: "Менеджер",
  client: "Клиент",
};

export const CLIENT_TYPE_LABELS: Record<ClientType, string> = {
  company: "Юридическое лицо",
  individual: "Физическое лицо",
  sole_proprietor: "Индивидуальный предприниматель",
};

export const MARK_TYPE_LABELS: Record<MarkType, string> = {
  word: "Словесный",
  figurative: "Изобразительный",
  combined: "Комбинированный",
  "3d": "Объёмный",
  sound: "Звуковой",
  color: "Цветовой",
  other: "Иной",
};

export const RISK_LABELS: Record<RiskLevel, string> = {
  low: "Низкий",
  medium: "Средний",
  high: "Высокий",
  critical: "Критический",
};

export const RISK_COLORS: Record<RiskLevel, string> = {
  low: "bg-green-100 text-green-800 dark:bg-green-900/30 dark:text-green-400",
  medium: "bg-amber-100 text-amber-800 dark:bg-amber-900/30 dark:text-amber-400",
  high: "bg-orange-100 text-orange-800 dark:bg-orange-900/30 dark:text-orange-400",
  critical: "bg-red-100 text-red-800 dark:bg-red-900/30 dark:text-red-400",
};

/** Срочность дела в работе поверенного. */
export type CasePriority = "low" | "medium" | "high";

export const PRIORITY_LABELS: Record<CasePriority, string> = {
  low: "Низкий",
  medium: "Средний",
  high: "Высокий",
};

export const PRIORITY_COLORS: Record<CasePriority, string> = {
  low: "bg-slate-500/15 text-slate-700 dark:text-slate-300",
  medium: "bg-blue-500/15 text-blue-700 dark:text-blue-400",
  high: "bg-red-500/15 text-red-700 dark:text-red-400",
};
