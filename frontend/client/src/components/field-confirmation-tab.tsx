import { useCallback, useEffect, useState } from "react";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Input } from "@/components/ui/input";
import { useToast } from "@/hooks/use-toast";
import { AiDisclaimer } from "@/components/ai-disclaimer";
import { cn } from "@/lib/utils";
import {
  api,
  ApiError,
  FIELD_STATUS_LABELS,
  type ReconciliationDto,
  type ReconciliationItemDto,
} from "@/lib/api";
import {
  AlertCircle,
  Check,
  CircleSlash,
  FileWarning,
  Loader2,
  Minus,
  Pencil,
  Plus,
  RefreshCw,
  Trash2,
  X,
} from "lucide-react";

const STATUS_STYLES: Record<string, string> = {
  matched: "bg-blue-500/15 text-blue-700 dark:text-blue-400",
  confirmed: "bg-emerald-500/15 text-emerald-700 dark:text-emerald-400",
  conflict: "bg-red-500/15 text-red-700 dark:text-red-400",
  needs_review: "bg-amber-500/15 text-amber-700 dark:text-amber-500",
  missing: "bg-muted text-muted-foreground",
  rejected: "bg-muted text-muted-foreground line-through",
  left_empty: "bg-muted text-muted-foreground",
};

const ACTION_LABELS: Record<string, string> = {
  accept: "Принять",
  edit: "Изменить",
  reject: "Отклонить",
  leave_empty: "Оставить пустым",
};

function maskIfSensitive(value: string | null, sensitive: boolean): string {
  if (!value) return "—";
  if (!sensitive) return value;
  if (value.length <= 2) return "*".repeat(value.length);
  return `${value[0]}${"*".repeat(value.length - 2)}${value[value.length - 1]}`;
}

export function FieldConfirmationTab({ appId }: { appId: number }) {
  const { toast } = useToast();
  const [data, setData] = useState<ReconciliationDto | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busyFieldId, setBusyFieldId] = useState<number | null>(null);
  const [editing, setEditing] = useState<Record<number, string>>({});
  const [revealed, setRevealed] = useState<Record<number, boolean>>({});

  const load = useCallback(async () => {
    setError(null);
    try {
      setData(await api.get<ReconciliationDto>(`/applications/${appId}/field-reconciliation`));
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "Не удалось загрузить сверку полей");
      setData(null);
    }
  }, [appId]);

  useEffect(() => {
    void load();
  }, [load]);

  /** Внести значение в поле, которого нет в документах, или своё поле. */
  const saveManual = async (
    fieldPath: string,
    label: string,
    value: string,
    isSensitive = false,
  ) => {
    try {
      await api.post(`/applications/${appId}/fields`, {
        field_path: fieldPath,
        label,
        value,
        is_sensitive: isSensitive,
      });
      toast({
        title: `Значение сохранено: ${label}`,
        description: "Введено вручную и считается подтверждённым.",
      });
      await load();
    } catch (e) {
      toast({
        title: "Не удалось сохранить значение",
        description: e instanceof ApiError ? e.message : "Неизвестная ошибка",
        variant: "destructive",
      });
    }
  };

  /** Отметить поле как незаполняемое в этом деле. */
  const skipField = async (fieldPath: string, label: string) => {
    try {
      await api.post(`/applications/${appId}/fields/skip`, {
        field_path: fieldPath,
        label,
      });
      toast({
        title: `Поле убрано: ${label}`,
        description: "Решение записано и его можно отменить.",
      });
      await load();
    } catch (e) {
      toast({
        title: "Не удалось убрать поле",
        description: e instanceof ApiError ? e.message : "Неизвестная ошибка",
        variant: "destructive",
      });
    }
  };

  /** Убрать поле, заведённое специалистом. */
  const removeField = async (fieldId: number, label: string) => {
    setBusyFieldId(fieldId);
    try {
      await api.delete(`/extracted-fields/${fieldId}`);
      toast({ title: `Поле удалено: ${label}` });
      await load();
    } catch (e) {
      toast({
        title: "Не удалось удалить поле",
        description: e instanceof ApiError ? e.message : "Неизвестная ошибка",
        variant: "destructive",
      });
    } finally {
      setBusyFieldId(null);
    }
  };

  const act = async (
    item: ReconciliationItemDto,
    action: string,
    payload: { value?: string; candidate_id?: number } = {},
  ) => {
    if (item.extracted_field_id == null) return;
    setBusyFieldId(item.extracted_field_id);
    try {
      await api.post(`/extracted-fields/${item.extracted_field_id}/confirm`, {
        action,
        ...payload,
      });
      toast({
        title: `${ACTION_LABELS[action] ?? action}: ${item.label}`,
        description: "Решение сохранено в истории поля.",
      });
      setEditing((prev) => {
        const next = { ...prev };
        delete next[item.extracted_field_id!];
        return next;
      });
      await load();
    } catch (e) {
      toast({
        title: "Не удалось сохранить решение",
        description: e instanceof ApiError ? e.message : "Неизвестная ошибка",
        variant: "destructive",
      });
    } finally {
      setBusyFieldId(null);
    }
  };

  // --- загрузка ---
  if (!data && !error) {
    return (
      <div className="flex items-center gap-2 py-10 justify-center text-muted-foreground">
        <Loader2 className="w-4 h-4 animate-spin" />
        <span className="text-sm">Загрузка сверки полей…</span>
      </div>
    );
  }

  // --- ошибка ---
  if (error) {
    return (
      <div className="space-y-3">
        <div className="flex items-start gap-2 rounded-md border border-destructive/40 bg-destructive/10 px-3 py-2">
          <AlertCircle className="w-4 h-4 shrink-0 mt-0.5 text-destructive" />
          <p className="flex-1 text-xs">{error}</p>
          <Button variant="ghost" size="sm" onClick={() => void load()}>
            Повторить
          </Button>
        </div>
      </div>
    );
  }

  const reconciliation = data!;
  const { summary, items } = reconciliation;

  // --- пусто: извлечение ещё не запускалось ---
  if (items.every((i) => i.extracted_field_id == null && !i.default_value)) {
    return (
      <Card className="border-dashed">
        <CardContent className="flex flex-col items-center justify-center py-10 text-center">
          <FileWarning className="w-8 h-8 text-muted-foreground mb-3" />
          <p className="text-sm font-medium">Реквизиты ещё не извлечены</p>
          <p className="text-xs text-muted-foreground mt-1 max-w-sm">
            Загрузите выписку на шаге выше и нажмите «Извлечь реквизиты».
          </p>
        </CardContent>
      </Card>
    );
  }

  return (
    <div className="space-y-5" data-testid="field-confirmation-tab">
      <AiDisclaimer compact />

      {/* --- сводка --- */}
      <Card className={cn("overflow-hidden", summary.can_generate_draft ? "border-emerald-500/35" : "border-primary/35")}>
        <CardContent className="flex flex-col gap-4 p-5 sm:flex-row sm:items-center">
          <div className={cn(
            "flex h-12 w-12 shrink-0 items-center justify-center rounded-full text-lg font-semibold",
            summary.can_generate_draft ? "bg-emerald-500/12 text-emerald-700" : "bg-primary/10 text-primary",
          )}>
            {summary.can_generate_draft ? <Check className="h-6 w-6" /> : summary.requires_attention}
          </div>
          <div className="min-w-0 flex-1">
            <p className="text-lg font-semibold">
              {summary.can_generate_draft
                ? "Данные проверены — можно формировать заявление"
                : attentionSummary(summary.requires_attention)}
            </p>
            {!summary.can_generate_draft && summary.blocking_document_generation.length > 0 && (
              <p className="mt-1 text-sm leading-relaxed text-muted-foreground">
                В первую очередь: {summary.blocking_document_generation.join(", ")}.
              </p>
            )}
          </div>
            <Button
              variant="ghost"
              className="shrink-0"
              onClick={() => void load()}
              data-testid="button-reload-reconciliation"
            >
              <RefreshCw className="w-3.5 h-3.5 mr-1.5" />
              Обновить
            </Button>
        </CardContent>
      </Card>

      {/* --- поля --- */}
      <div className="space-y-3">
        {items.map((item, index) => {
          const fieldId = item.extracted_field_id;
          const isBusy = busyFieldId != null && busyFieldId === fieldId;
          const isEditing = fieldId != null && fieldId in editing;
          const displayValue = item.registry_value ?? item.default_value;
          const isRevealed = fieldId != null && revealed[fieldId];

          return (
            <Card
              key={`${item.case_field}-${index}`}
              className={cn(
                "overflow-hidden",
                item.blocks_document_generation && "border-l-4 border-l-amber-500",
                item.status === "confirmed" && "border-l-4 border-l-emerald-500/70",
              )}
              data-testid={`field-row-${item.case_field}`}
            >
              <CardContent className="space-y-4 p-5">
                <div className="flex flex-wrap items-center gap-2">
                  <span className="text-base font-semibold">{item.label}</span>
                  <Badge className={cn(STATUS_STYLES[item.status])}>
                    {FIELD_STATUS_LABELS[item.status] ?? item.status}
                  </Badge>
                  {item.required_for_application && (
                    <Badge variant="outline">
                      обязательное
                    </Badge>
                  )}
                  {item.is_sensitive && (
                    <Badge variant="outline">
                      персональные данные
                    </Badge>
                  )}
                </div>

                {/* The working view shows the decision, not extraction internals. */}
                <div className="rounded-xl bg-muted/55 px-4 py-3">
                    <p className="text-xs font-medium uppercase tracking-[0.08em] text-muted-foreground">Предлагаемое значение</p>
                    <p className="mt-1 break-words text-base font-medium leading-relaxed">
                      {item.is_sensitive && !isRevealed
                        ? maskIfSensitive(displayValue, true)
                        : displayValue ?? "—"}
                      {item.is_sensitive && fieldId != null && (
                        <button
                          type="button"
                          className="ml-3 text-xs font-normal text-primary hover:underline"
                          onClick={() =>
                            setRevealed((p) => ({ ...p, [fieldId]: !p[fieldId] }))
                          }
                        >
                          {isRevealed ? "скрыть" : "показать"}
                        </button>
                      )}
                    </p>
                </div>

                {item.case_value && item.case_value !== displayValue && (
                  <div className="flex flex-col gap-1 rounded-lg border border-amber-500/35 bg-amber-500/[0.06] px-4 py-3 sm:flex-row sm:items-center sm:justify-between">
                    <span className="text-sm font-medium text-amber-800">В карточке уже записано другое значение</span>
                    <span className="break-all text-sm">{item.case_value}</span>
                  </div>
                )}

                {item.validation_error && (
                  <p className="text-sm text-amber-700 dark:text-amber-500">
                    {item.validation_error}
                  </p>
                )}
                {item.note && (
                  <p className="text-sm text-muted-foreground">{item.note}</p>
                )}

                {/* Конкурирующие кандидаты */}
                {item.candidates.length > 1 &&
                  new Set(item.candidates.map((c) => c.normalized_value)).size > 1 && (
                    <div className="space-y-2 rounded-lg border border-border p-4">
                      <p className="text-sm font-semibold">
                        Найдено несколько значений — выберите верное:
                      </p>
                      {item.candidates.map((candidate) => (
                        <div
                          key={candidate.id}
                          className="flex items-center justify-between gap-2"
                        >
                          <span className="break-all text-sm">
                            {candidate.normalized_value ?? candidate.raw_value}
                          </span>
                          <Button
                            size="sm"
                            variant="outline"
                            disabled={isBusy}
                            onClick={() =>
                              void act(item, "accept", { candidate_id: candidate.id })
                            }
                            data-testid={`button-pick-candidate-${candidate.id}`}
                          >
                            Выбрать
                          </Button>
                        </div>
                      ))}
                    </div>
                  )}

                {/* Ввод значения вручную */}
                {isEditing && fieldId != null && (
                  <div className="flex items-center gap-2">
                    <Input
                      value={editing[fieldId]}
                      onChange={(e) =>
                        setEditing((p) => ({ ...p, [fieldId]: e.target.value }))
                      }
                      placeholder="Введите значение"
                      className="text-base"
                      data-testid={`input-edit-${fieldId}`}
                    />
                    <Button
                      size="sm"
                      disabled={isBusy || !editing[fieldId]?.trim()}
                      onClick={() =>
                        void act(item, "edit", { value: editing[fieldId] })
                      }
                      data-testid={`button-save-edit-${fieldId}`}
                    >
                      Сохранить
                    </Button>
                    <Button
                      size="sm"
                      variant="ghost"
                      onClick={() =>
                        setEditing((p) => {
                          const next = { ...p };
                          delete next[fieldId];
                          return next;
                        })
                      }
                    >
                      Отмена
                    </Button>
                  </div>
                )}

                {/* Своё поле можно убрать целиком: извлечённое —
                    только отклонить, чтобы решение осталось в истории. */}
                {fieldId != null && item.extraction_method === "manual" && (
                  <div className="pt-1">
                    <Button
                      size="sm"
                      variant="ghost"
                      className="text-sm text-muted-foreground"
                      disabled={isBusy}
                      onClick={() => void removeField(fieldId, item.label)}
                      data-testid={`delete-field-${fieldId}`}
                    >
                      <Trash2 className="w-3 h-3 mr-1" />
                      Удалить поле
                    </Button>
                  </div>
                )}

                {/* Действия специалиста */}
                {fieldId != null && !isEditing && (
                  <div className="flex flex-wrap items-center gap-2 pt-1">
                    {item.available_actions.includes("accept") && (
                      <Button
                        size="sm"
                        variant="default"
                        disabled={isBusy || item.status === "confirmed"}
                        onClick={() => void act(item, "accept")}
                        data-testid={`button-accept-${item.case_field}`}
                      >
                        {isBusy ? (
                          <Loader2 className="w-3.5 h-3.5 mr-1.5 animate-spin" />
                        ) : (
                          <Check className="w-3.5 h-3.5 mr-1.5" />
                        )}
                        Принять
                      </Button>
                    )}
                    {item.available_actions.includes("edit") && (
                      <Button
                        size="sm"
                        variant="outline"
                        disabled={isBusy}
                        onClick={() =>
                          setEditing((p) => ({
                            ...p,
                            [fieldId]: item.registry_value ?? "",
                          }))
                        }
                        data-testid={`button-edit-${item.case_field}`}
                      >
                        <Pencil className="w-3.5 h-3.5 mr-1.5" />
                        Изменить
                      </Button>
                    )}
                    {item.available_actions.includes("reject") && (
                      <Button
                        size="sm"
                        variant="ghost"
                        disabled={isBusy}
                        onClick={() => void act(item, "reject")}
                        data-testid={`button-reject-${item.case_field}`}
                      >
                        <X className="w-3.5 h-3.5 mr-1.5" />
                        Отклонить
                      </Button>
                    )}
                    {item.available_actions.includes("leave_empty") && (
                      <Button
                        size="sm"
                        variant="ghost"
                        disabled={isBusy}
                        onClick={() => void act(item, "leave_empty")}
                        data-testid={`button-leave-empty-${item.case_field}`}
                      >
                        <Minus className="w-3.5 h-3.5 mr-1.5" />
                        Оставить пустым
                      </Button>
                    )}
                  </div>
                )}

                {/* Поле без записи в БД: значение вводится вручную.
                    Раньше здесь не было ничего, кроме пояснения, и
                    заполнить такое поле было негде. */}
                {fieldId == null && (
                  <ManualEntry
                    label={item.label}
                    fieldPath={item.registry_field ?? item.case_field}
                    isSensitive={item.is_sensitive}
                    canSkip={!item.required_for_application}
                    onSave={(value) =>
                      void saveManual(
                        item.registry_field ?? item.case_field,
                        item.label,
                        value,
                        item.is_sensitive,
                      )
                    }
                    onSkip={() =>
                      void skipField(
                        item.registry_field ?? item.case_field,
                        item.label,
                      )
                    }
                  />
                )}
              </CardContent>
            </Card>
          );
        })}
      </div>

      <AddCustomField
        onAdd={(label, value) =>
          void saveManual(
            `custom.${label.toLowerCase().replace(/\s+/g, "_")}`,
            label,
            value,
          )
        }
      />

    </div>
  );
}

function attentionSummary(value: number): string {
  const mod100 = value % 100;
  const mod10 = value % 10;
  if (mod100 >= 11 && mod100 <= 14) return `${value} полей требуют решения`;
  if (mod10 === 1) return `${value} поле требует решения`;
  if (mod10 >= 2 && mod10 <= 4) return `${value} поля требуют решения`;
  return `${value} полей требуют решения`;
}

/**
 * Ввод значения в поле, которого не нашлось в документах.
 *
 * Такое поле не имеет записи в базе, поэтому раньше заполнить его
 * было негде — приходилось искать другое место в системе. Значение,
 * введённое здесь, сразу считается подтверждённым: его внёс человек.
 */
function ManualEntry({
  label,
  fieldPath,
  isSensitive,
  canSkip,
  onSave,
  onSkip,
}: {
  label: string;
  fieldPath: string;
  isSensitive: boolean;
  canSkip: boolean;
  onSave: (value: string) => void;
  onSkip: () => void;
}) {
  const [isOpen, setIsOpen] = useState(false);
  const [value, setValue] = useState("");

  if (!isOpen) {
    return (
      <div className="flex items-center gap-2 pt-1">
        <p className="flex items-center gap-1.5 text-sm text-muted-foreground">
          <CircleSlash className="w-3.5 h-3.5" />
          Значение не извлечено из документа
        </p>
        <Button
          size="sm"
          variant="outline"
          className="text-sm"
          onClick={() => setIsOpen(true)}
          data-testid={`manual-entry-${fieldPath}`}
        >
          <Pencil className="w-3 h-3 mr-1" />
          Ввести вручную
        </Button>
        {/* Обязательное поле бланка убрать нельзя: заявление
            окажется неполным, а система этого не покажет. */}
        {canSkip && (
          <Button
            size="sm"
            variant="ghost"
            className="text-sm text-muted-foreground"
            onClick={onSkip}
            data-testid={`skip-${fieldPath}`}
          >
            <Trash2 className="w-3 h-3 mr-1" />
            Убрать
          </Button>
        )}
      </div>
    );
  }

  return (
    <div className="flex items-center gap-2 pt-1">
      <Input
        autoFocus
        value={value}
        onChange={(e) => setValue(e.target.value)}
        placeholder={`${label}${isSensitive ? " (персональные данные)" : ""}`}
        className="text-base"
        data-testid={`manual-input-${fieldPath}`}
      />
      <Button
        size="sm"
        disabled={!value.trim()}
        onClick={() => {
          onSave(value.trim());
          setIsOpen(false);
          setValue("");
        }}
        data-testid={`manual-save-${fieldPath}`}
      >
        Сохранить
      </Button>
      <Button size="sm" variant="ghost" onClick={() => setIsOpen(false)}>
        Отмена
      </Button>
    </div>
  );
}

/**
 * Своё поле специалиста.
 *
 * Маппинг покрывает бланк заявления, но в деле бывают сведения,
 * которых в нём нет. Такое поле помечается как добавленное вручную
 * и в заявление не попадает — оно живёт в карточке дела.
 */
function AddCustomField({
  onAdd,
}: {
  onAdd: (label: string, value: string) => void;
}) {
  const [isOpen, setIsOpen] = useState(false);
  const [label, setLabel] = useState("");
  const [value, setValue] = useState("");

  if (!isOpen) {
    return (
      <Button
        size="sm"
        variant="outline"
        onClick={() => setIsOpen(true)}
        data-testid="add-custom-field"
      >
        <Plus className="w-3.5 h-3.5 mr-1.5" />
        Добавить своё поле
      </Button>
    );
  }

  return (
    <Card>
      <CardContent className="flex flex-wrap items-center gap-3 p-4">
        <Input
          autoFocus
          value={label}
          onChange={(e) => setLabel(e.target.value)}
          placeholder="Название поля"
          className="w-60 text-base"
          data-testid="custom-field-label"
        />
        <Input
          value={value}
          onChange={(e) => setValue(e.target.value)}
          placeholder="Значение"
          className="min-w-[180px] flex-1 text-base"
          data-testid="custom-field-value"
        />
        <Button
          size="sm"
          disabled={!label.trim() || !value.trim()}
          onClick={() => {
            onAdd(label.trim(), value.trim());
            setIsOpen(false);
            setLabel("");
            setValue("");
          }}
          data-testid="custom-field-save"
        >
          Добавить
        </Button>
        <Button size="sm" variant="ghost" onClick={() => setIsOpen(false)}>
          Отмена
        </Button>
      </CardContent>
    </Card>
  );
}
