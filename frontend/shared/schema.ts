import { z } from "zod";

// ========== ENUMS ==========

export const ApplicationStatusEnum = z.enum([
  "draft",
  "awaiting_client_data",
  "intake_review",
  "legal_precheck_running",
  "awaiting_lawyer_review",
  "classes_review",
  "conflict_search_running",
  "recommendation_ready",
  "docs_preparation",
  "awaiting_doc_approval",
  "ready_for_submission",
  "submitted",
  "status_monitoring",
  "office_action_received",
  "client_action_required",
  "completed",
  "rejected",
  "archived",
]);
export type ApplicationStatus = z.infer<typeof ApplicationStatusEnum>;

export const UserRoleEnum = z.enum(["admin", "lawyer", "manager", "client"]);
export type UserRole = z.infer<typeof UserRoleEnum>;

export const ClientTypeEnum = z.enum(["company", "individual", "sole_proprietor"]);
export type ClientType = z.infer<typeof ClientTypeEnum>;

export const MarkTypeEnum = z.enum(["word", "figurative", "combined", "three_d", "sound", "color", "other"]);
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
  inn: string;
  ogrnOrOgrnip: string;
  createdAt: string;
}

export interface Application {
  id: number;
  clientId: number;
  status: ApplicationStatus;
  markType: MarkType;
  markName: string;
  markText: string;
  colorsClaimed: string;
  transliteration: string;
  translation: string;
  descriptionOfMark: string;
  businessDescription: string;
  goodsServicesRaw: string;
  territory: string;
  priorityClaim: string;
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
  awaiting_client_data: "Ожидание данных клиента",
  intake_review: "Первичная проверка",
  legal_precheck_running: "Правовой предварительный анализ",
  awaiting_lawyer_review: "На рассмотрении юриста",
  classes_review: "Проверка классов МКТУ",
  conflict_search_running: "Поиск конфликтов",
  recommendation_ready: "Рекомендации готовы",
  docs_preparation: "Подготовка документов",
  awaiting_doc_approval: "Утверждение документов",
  ready_for_submission: "Готова к подаче",
  submitted: "Подана",
  status_monitoring: "Мониторинг статуса",
  office_action_received: "Получено уведомление ФИПС",
  client_action_required: "Требуется действие клиента",
  completed: "Завершена",
  rejected: "Отклонена",
  archived: "В архиве",
};

export const STATUS_COLORS: Record<ApplicationStatus, string> = {
  draft: "bg-slate-100 text-slate-700 dark:bg-slate-800 dark:text-slate-300",
  awaiting_client_data: "bg-amber-100 text-amber-800 dark:bg-amber-900/30 dark:text-amber-400",
  intake_review: "bg-blue-100 text-blue-800 dark:bg-blue-900/30 dark:text-blue-400",
  legal_precheck_running: "bg-violet-100 text-violet-800 dark:bg-violet-900/30 dark:text-violet-400",
  awaiting_lawyer_review: "bg-orange-100 text-orange-800 dark:bg-orange-900/30 dark:text-orange-400",
  classes_review: "bg-cyan-100 text-cyan-800 dark:bg-cyan-900/30 dark:text-cyan-400",
  conflict_search_running: "bg-indigo-100 text-indigo-800 dark:bg-indigo-900/30 dark:text-indigo-400",
  recommendation_ready: "bg-teal-100 text-teal-800 dark:bg-teal-900/30 dark:text-teal-400",
  docs_preparation: "bg-blue-100 text-blue-800 dark:bg-blue-900/30 dark:text-blue-400",
  awaiting_doc_approval: "bg-amber-100 text-amber-800 dark:bg-amber-900/30 dark:text-amber-400",
  ready_for_submission: "bg-emerald-100 text-emerald-800 dark:bg-emerald-900/30 dark:text-emerald-400",
  submitted: "bg-green-100 text-green-800 dark:bg-green-900/30 dark:text-green-400",
  status_monitoring: "bg-sky-100 text-sky-800 dark:bg-sky-900/30 dark:text-sky-400",
  office_action_received: "bg-red-100 text-red-800 dark:bg-red-900/30 dark:text-red-400",
  client_action_required: "bg-rose-100 text-rose-800 dark:bg-rose-900/30 dark:text-rose-400",
  completed: "bg-green-100 text-green-800 dark:bg-green-900/30 dark:text-green-400",
  rejected: "bg-red-100 text-red-800 dark:bg-red-900/30 dark:text-red-400",
  archived: "bg-gray-100 text-gray-600 dark:bg-gray-800 dark:text-gray-400",
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
  three_d: "Объёмный",
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
