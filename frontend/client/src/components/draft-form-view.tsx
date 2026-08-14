/**
 * Бланк заявления — единственное место работы с полями.
 *
 * Раньше сверка полей и черновик были разными вкладками, хотя правили
 * одни и те же значения: одна показывала, что извлечено из документов,
 * другая — что попадёт в заявление. Теперь это один экран в структуре
 * официальной формы, где у каждого поля видно и значение, и откуда оно
 * взялось, и что с ним делать.
 *
 * Цвет и пометки несут смысл: зелёное — подтверждено и уйдёт в бланк,
 * красное — обязательное поле, без которого заявление не подать,
 * серое — необязательное и пустое.
 */

import { useState } from "react";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import { useToast } from "@/hooks/use-toast";
import { AsyncSection } from "@/components/async-states";
import { api, ApiError } from "@/lib/api";
import { useApi } from "@/lib/use-api";
import { cn } from "@/lib/utils";
import {
  AlertCircle,
  Check,
  Eye,
  EyeOff,
  Info,
  Pencil,
  Trash2,
  X,
} from "lucide-react";

interface Candidate {
  raw_value: string;
  normalized_value: string | null;
  page_number: number | null;
  /** Страницы, где встретилось это же значение. */
  pages?: number[];
  validation_passed: boolean | null;
}

interface FormField {
  inid: string | null;
  label: string;
  source: string | null;
  fill: string;
  value: string | null;
  hint: string | null;
  multiline: boolean;
  is_filled: boolean;
  editable: boolean;
  status: string | null;
  required: boolean;
  needs_attention: boolean;
  origin: string | null;
  page_number: number | null;
  is_sensitive: boolean;
  validation_error: string | null;
  extracted_field_id: number | null;
  field_path: string | null;
  candidates: Candidate[];
  actions: string[];
}

interface FormSection {
  id: string;
  title: string;
  readonly: boolean;
  fields: FormField[];
  filled_count: number;
  total_count: number;
}

interface DraftFormDto {
  title: string;
  sections: FormSection[];
  filled_count: number;
  total_count: number;
  required_count: number;
  required_done: number;
  blocking: string[];
  can_generate: boolean;
  notice: string;
}

const FILL_LABELS: Record<string, string> = {
  manual: "Заполняет специалист",
  checkbox: "Отмечает специалист в бланке",
  office: "Заполняет Роспатент",
  classes: "Из подтверждённых классов МКТУ",
};

const STATUS_LABELS: Record<string, string> = {
  confirmed: "подтверждено",
  matched: "найдено, не подтверждено",
  conflict: "несколько значений",
  needs_review: "требует проверки",
  missing: "не найдено",
  rejected: "отклонено",
  left_empty: "оставлено пустым",
};

export function DraftFormView({ appId }: { appId: number }) {
  const { toast } = useToast();
  const state = useApi<DraftFormDto>(`/applications/${appId}/draft-form`);
  const [busy, setBusy] = useState<string | null>(null);

  const fail = (e: unknown, title: string) =>
    toast({
      title,
      description: e instanceof ApiError ? e.message : "Неизвестная ошибка",
      variant: "destructive",
    });

  /** Сохранить значение: годится и для правки, и для пустого поля. */
  const save = async (field: FormField, value: string) => {
    if (!field.field_path && !field.source) return;
    setBusy(field.label);
    try {
      await api.post(`/applications/${appId}/fields`, {
        field_path: field.field_path ?? field.source,
        label: field.label,
        value,
        is_sensitive: field.is_sensitive,
      });
      toast({ title: `Сохранено: ${field.label}` });
      state.reload();
    } catch (e) {
      fail(e, "Не удалось сохранить");
    } finally {
      setBusy(null);
    }
  };

  /** Принять найденное значение или выбрать один из вариантов. */
  const confirm = async (field: FormField, candidateIndex?: number) => {
    if (field.extracted_field_id == null) return;
    setBusy(field.label);
    try {
      await api.post(`/extracted-fields/${field.extracted_field_id}/confirm`, {
        action: "accept",
        ...(candidateIndex != null
          ? { value: field.candidates[candidateIndex].normalized_value }
          : {}),
      });
      toast({ title: `Подтверждено: ${field.label}` });
      state.reload();
    } catch (e) {
      fail(e, "Не удалось подтвердить");
    } finally {
      setBusy(null);
    }
  };

  const clear = async (field: FormField) => {
    if (field.extracted_field_id == null) return;
    setBusy(field.label);
    try {
      await api.delete(`/extracted-fields/${field.extracted_field_id}`);
      toast({ title: `Очищено: ${field.label}` });
      state.reload();
    } catch (e) {
      fail(e, "Не удалось очистить поле");
    } finally {
      setBusy(null);
    }
  };

  return (
    <AsyncSection
      state={state}
      loadingLabel="Загрузка бланка…"
      emptyTitle="Бланк недоступен"
    >
      {(data) => (
        <div className="space-y-3">
          {(() => {
            const manualPending = data.sections
              .flatMap((section) => section.fields)
              .filter(
                (field) =>
                  (field.fill === "manual" || field.fill === "checkbox") &&
                  (!field.is_filled || field.needs_attention),
              );
            if (manualPending.length === 0) return null;
            return (
              <div className="rounded-lg border-2 border-amber-500/50 bg-amber-500/[0.08] p-4">
                <div className="flex items-start gap-3">
                  <span className="flex h-9 w-9 shrink-0 items-center justify-center rounded-full bg-amber-500/15 text-amber-800 dark:text-amber-300">
                    <Pencil className="h-4 w-4" />
                  </span>
                  <div className="min-w-0">
                    <h3 className="text-sm font-semibold text-amber-950 dark:text-amber-200">
                      Нужно заполнить вручную: {manualPending.length}
                    </h3>
                    <p className="mt-1 text-xs leading-5 text-amber-900/80 dark:text-amber-200/80">
                      Эти поля не заполняются автоматически. В бланке они выделены янтарным цветом и подписаны «Заполняет специалист».
                    </p>
                    <div className="mt-2 flex flex-wrap gap-1.5">
                      {manualPending.slice(0, 6).map((field) => (
                        <Badge
                          key={`${field.source ?? field.label}-${field.label}`}
                          variant="outline"
                          className="border-amber-500/40 bg-background/70 text-[10px] text-amber-950 dark:text-amber-200"
                        >
                          {field.label}
                        </Badge>
                      ))}
                      {manualPending.length > 6 && (
                        <Badge variant="outline" className="border-amber-500/40 bg-background/70 text-[10px]">
                          ещё {manualPending.length - 6}
                        </Badge>
                      )}
                    </div>
                  </div>
                </div>
              </div>
            );
          })()}

          {/* Шапка бланка со сводкой готовности */}
          <div className="rounded-lg border-2 border-foreground/70 bg-background">
            <div className="border-b-2 border-foreground/70 px-4 py-3 text-center">
              <p className="text-sm font-bold uppercase tracking-wide">
                {data.title}
              </p>
            </div>

            <div className="px-4 py-3 space-y-2">
              <div className="flex flex-wrap items-center gap-2">
                <Badge
                  className={cn(
                    "text-[11px]",
                    data.can_generate
                      ? "bg-emerald-500/15 text-emerald-700 dark:text-emerald-400"
                      : "bg-red-500/15 text-red-700 dark:text-red-400",
                  )}
                >
                  {data.can_generate
                    ? "Обязательные поля заполнены"
                    : `Не хватает обязательных: ${data.blocking.length}`}
                </Badge>
                <span className="text-[11px] text-muted-foreground">
                  обязательных {data.required_done} из {data.required_count} ·
                  всего заполнено {data.filled_count} из {data.total_count}
                </span>
              </div>

              {/* Полоса готовности по обязательным полям. */}
              <div className="h-1.5 rounded-full bg-muted overflow-hidden">
                <div
                  className={cn(
                    "h-full transition-all",
                    data.can_generate ? "bg-emerald-500" : "bg-amber-500",
                  )}
                  style={{
                    width: `${
                      data.required_count
                        ? (data.required_done / data.required_count) * 100
                        : 100
                    }%`,
                  }}
                />
              </div>

              {data.blocking.length > 0 && (
                <p className="text-[11px] text-muted-foreground">
                  <AlertCircle className="w-3 h-3 inline mr-1 text-red-600" />
                  Без этих полей заявление подавать нельзя:{" "}
                  {data.blocking.join(", ")}
                </p>
              )}

              <p className="text-[10px] text-muted-foreground flex items-start gap-1">
                <Info className="w-3 h-3 mt-0.5 shrink-0" />
                {data.notice}
              </p>
            </div>
          </div>

          {data.sections.map((section) => (
            <div
              key={section.id}
              className="rounded-lg border-2 border-foreground/40 overflow-hidden"
            >
              <div className="flex items-center gap-2 bg-muted/60 px-3 py-1.5 border-b-2 border-foreground/40">
                <span className="text-xs font-bold uppercase">
                  {section.title}
                </span>
                <Badge variant="secondary" className="text-[10px] ml-auto">
                  {section.filled_count}/{section.total_count}
                </Badge>
              </div>

              <div className="divide-y divide-border">
                {section.fields.map((field, index) => (
                  <FormRow
                    key={`${section.id}-${index}`}
                    field={field}
                    isBusy={busy === field.label}
                    onSave={(value) => void save(field, value)}
                    onConfirm={(i) => void confirm(field, i)}
                    onClear={() => void clear(field)}
                  />
                ))}
              </div>
            </div>
          ))}
        </div>
      )}
    </AsyncSection>
  );
}

function FormRow({
  field,
  isBusy,
  onSave,
  onConfirm,
  onClear,
}: {
  field: FormField;
  isBusy: boolean;
  onSave: (value: string) => void;
  onConfirm: (candidateIndex?: number) => void;
  onClear: () => void;
}) {
  const [isEditing, setIsEditing] = useState(false);
  const [draft, setDraft] = useState(field.value ?? "");
  const [revealed, setRevealed] = useState(false);

  const canEdit = field.editable && field.fill !== "classes";
  const confirmed = field.status === "confirmed";
  const canConfirm =
    field.extracted_field_id != null && !confirmed && field.is_filled;
  const requiresManualAction =
    field.fill === "manual" || field.fill === "checkbox";
  const responsibility = requiresManualAction
    ? FILL_LABELS[field.fill]
    : field.fill === "auto"
      ? field.origin
        ? `Источник: ${field.origin}${field.page_number ? `, стр. ${field.page_number}` : ""}`
        : "Из подтверждённых данных проекта"
      : FILL_LABELS[field.fill] ?? field.fill;

  // Персональные данные по умолчанию скрыты.
  const shown =
    field.is_sensitive && !revealed && field.value
      ? `${field.value[0]}${"*".repeat(Math.max(field.value.length - 2, 1))}${
          field.value.length > 1 ? field.value[field.value.length - 1] : ""
        }`
      : field.value;

  return (
    <div
      className={cn(
        "flex items-start gap-3 border-l-4 px-3 py-3",
        confirmed && "bg-emerald-500/5",
        requiresManualAction
          ? "border-l-amber-500 bg-amber-500/[0.06]"
          : "border-l-transparent",
        field.needs_attention && "border-l-red-500 bg-red-500/[0.07]",
      )}
      data-testid={`form-field-${field.source ?? field.label}`}
    >
      {/* Код INID — как в левой колонке бланка */}
      <div className="w-14 shrink-0 pt-0.5">
        {field.inid ? (
          <span className="inline-block rounded border border-foreground/40 px-1 text-[10px] font-mono">
            {field.inid}
          </span>
        ) : (
          <span className="text-[10px] text-muted-foreground">—</span>
        )}
      </div>

      <div className="min-w-0 flex-1 space-y-1">
        <div className="flex flex-wrap items-center gap-2">
          <span className="text-xs font-medium">{field.label}</span>

          <Badge
            variant="outline"
            className={cn(
              "text-[10px] font-medium",
              requiresManualAction
                ? "border-amber-500/50 bg-amber-500/10 text-amber-900 dark:text-amber-200"
                : field.fill === "office"
                  ? "border-slate-400/50 bg-slate-500/10 text-slate-700 dark:text-slate-300"
                  : "border-sky-500/40 bg-sky-500/[0.08] text-sky-800 dark:text-sky-300",
            )}
          >
            {responsibility}
          </Badge>

          {field.required && (
            <Badge
              className={cn(
                "text-[10px]",
                confirmed
                  ? "bg-emerald-500/15 text-emerald-700 dark:text-emerald-400"
                  : "bg-red-500/15 text-red-700 dark:text-red-400",
              )}
            >
              обязательное
            </Badge>
          )}

          {confirmed && (
            <span className="inline-flex items-center gap-1 text-[10px] text-emerald-700 dark:text-emerald-400">
              <Check className="w-3 h-3" />
              подтверждено
            </span>
          )}

          {!confirmed && field.status && field.status !== "missing" && (
            <span className="text-[10px] text-amber-700 dark:text-amber-500">
              {STATUS_LABELS[field.status] ?? field.status}
            </span>
          )}

        </div>

        {isEditing ? (
          <div className="flex items-start gap-2">
            {field.multiline ? (
              <Textarea
                autoFocus
                value={draft}
                onChange={(e) => setDraft(e.target.value)}
                rows={2}
                className="text-xs"
              />
            ) : (
              <Input
                autoFocus
                value={draft}
                onChange={(e) => setDraft(e.target.value)}
                className="h-8 text-xs"
              />
            )}
            <Button
              size="sm"
              className="h-8 text-[11px] shrink-0"
              disabled={isBusy || !draft.trim()}
              onClick={() => {
                onSave(draft.trim());
                setIsEditing(false);
              }}
            >
              Сохранить
            </Button>
            <Button
              size="sm"
              variant="ghost"
              className="h-8 text-[11px] shrink-0"
              onClick={() => {
                setIsEditing(false);
                setDraft(field.value ?? "");
              }}
            >
              Отмена
            </Button>
          </div>
        ) : (
          <div className="flex items-start gap-2">
            <p
              className={cn(
                "text-xs flex-1 min-h-[1.2rem] rounded border border-dashed px-2 py-1",
                field.is_filled
                  ? "border-transparent"
                  : field.required
                    ? "border-red-500/40 text-red-700 dark:text-red-400"
                    : "border-border text-muted-foreground",
              )}
            >
              {shown ?? (field.required ? "не заполнено — требуется" : "не заполнено")}
            </p>

            {field.is_sensitive && field.value && (
              <button
                type="button"
                className="p-1 text-muted-foreground hover:text-foreground shrink-0"
                onClick={() => setRevealed((v) => !v)}
                title={revealed ? "Скрыть" : "Показать"}
              >
                {revealed ? (
                  <EyeOff className="w-3.5 h-3.5" />
                ) : (
                  <Eye className="w-3.5 h-3.5" />
                )}
              </button>
            )}

            {canConfirm && (
              <Button
                size="sm"
                className="h-7 text-[11px] shrink-0 bg-emerald-600 hover:bg-emerald-700 text-white"
                disabled={isBusy}
                onClick={() => onConfirm()}
                data-testid={`confirm-${field.source}`}
              >
                <Check className="w-3 h-3 mr-1" />
                Принять
              </Button>
            )}

            {canEdit && (
              <Button
                size="sm"
                variant="ghost"
                className="h-7 text-[11px] shrink-0"
                disabled={isBusy}
                onClick={() => setIsEditing(true)}
                data-testid={`edit-${field.source}`}
              >
                <Pencil className="w-3 h-3 mr-1" />
                {field.is_filled ? "Изменить" : "Заполнить"}
              </Button>
            )}

            {field.extracted_field_id != null && field.origin === "введено вручную" && (
              <Button
                size="sm"
                variant="ghost"
                className="h-7 w-7 p-0 shrink-0 text-muted-foreground hover:text-destructive"
                disabled={isBusy}
                onClick={onClear}
                title="Очистить поле"
              >
                <Trash2 className="w-3.5 h-3.5" />
              </Button>
            )}
          </div>
        )}

        {/* Одно значение, найденное на нескольких страницах, —
            подтверждение, а не повод выбирать. */}
        {field.candidates.length === 1 &&
          (field.candidates[0].pages?.length ?? 0) > 1 && (
            <p className="text-[10px] text-muted-foreground">
              значение совпало на страницах:{" "}
              {field.candidates[0].pages!.join(", ")}
            </p>
          )}

        {/* Выбор предлагается, только если значения действительно разные. */}
        {field.candidates.length > 1 && !confirmed && (
          <div className="rounded-md border border-amber-500/40 bg-amber-500/5 p-2 space-y-1">
            <p className="text-[10px] font-medium">
              В документе найдено несколько значений — выберите верное:
            </p>
            {field.candidates.map((candidate, index) => (
              <div key={index} className="flex items-center gap-2">
                <span className="text-[11px] font-mono flex-1">
                  {candidate.normalized_value ?? candidate.raw_value}
                  {(candidate.pages?.length ?? 0) > 1
                    ? ` · стр. ${candidate.pages!.join(", ")}`
                    : candidate.page_number
                      ? ` · стр. ${candidate.page_number}`
                      : ""}
                  {candidate.validation_passed === false
                    ? " · не прошло проверку"
                    : ""}
                </span>
                <Button
                  size="sm"
                  variant="outline"
                  className="h-6 text-[10px]"
                  disabled={isBusy}
                  onClick={() => onConfirm(index)}
                >
                  Выбрать
                </Button>
              </div>
            ))}
          </div>
        )}

        {field.validation_error && (
          <p className="text-[10px] text-amber-700 dark:text-amber-500 flex items-start gap-1">
            <AlertCircle className="w-3 h-3 mt-0.5 shrink-0" />
            {field.validation_error}
          </p>
        )}

        <div className="flex flex-wrap items-center gap-2">
          {field.origin && requiresManualAction && (
            <span className="text-[10px] text-muted-foreground">
              Предзаполнено: {field.origin}
              {field.page_number ? `, стр. ${field.page_number}` : ""}
            </span>
          )}
          {field.hint && (
            <span className="text-[10px] text-muted-foreground">{field.hint}</span>
          )}
        </div>
      </div>
    </div>
  );
}
