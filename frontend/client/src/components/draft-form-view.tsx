/**
 * Интерактивный бланк заявления.
 *
 * Повторяет структуру официальной формы Роспатента: те же разделы
 * в том же порядке, те же коды INID в рамках слева. Специалист видит
 * документ таким, каким он уйдёт в ведомство, и заполняет недостающее
 * прямо здесь, не переключаясь между вкладками.
 *
 * Цвет здесь тоже несёт смысл: заполненное поле выделено, пустое
 * обязательное — заметно, а то, что вносится только вручную
 * (вид знака, приоритет, пошлина), помечено отдельно, чтобы это
 * не выглядело недоработкой системы.
 */

import { useState } from "react";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import { useToast } from "@/hooks/use-toast";
import { AsyncSection } from "@/components/async-states";
import { api, ApiError } from "@/lib/api";
import { useApi } from "@/lib/use-api";
import { cn } from "@/lib/utils";
import { Check, Pencil, Info } from "lucide-react";

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
  notice: string;
}

const FILL_LABELS: Record<string, string> = {
  manual: "заполняется вручную",
  checkbox: "отметка в бланке",
  office: "заполняет Роспатент",
  classes: "из перечня классов",
};

export function DraftFormView({ appId }: { appId: number }) {
  const { toast } = useToast();
  const state = useApi<DraftFormDto>(`/applications/${appId}/draft-form`);
  const [saving, setSaving] = useState<string | null>(null);

  const save = async (field: FormField, value: string) => {
    if (!field.source) return;
    setSaving(field.source);
    try {
      await api.post(`/applications/${appId}/fields`, {
        field_path: field.source,
        label: field.label,
        value,
      });
      toast({ title: `Сохранено: ${field.label}` });
      state.reload();
    } catch (e) {
      toast({
        title: "Не удалось сохранить",
        description: e instanceof ApiError ? e.message : "Неизвестная ошибка",
        variant: "destructive",
      });
    } finally {
      setSaving(null);
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
          {/* Шапка как в бланке */}
          <div className="rounded-lg border-2 border-foreground/70 bg-background">
            <div className="border-b-2 border-foreground/70 px-4 py-3 text-center">
              <p className="text-sm font-bold uppercase tracking-wide">
                {data.title}
              </p>
            </div>
            <div className="px-4 py-2 flex flex-wrap items-center gap-x-4 gap-y-1 text-[11px] text-muted-foreground">
              <span>
                Заполнено полей: {data.filled_count} из {data.total_count}
              </span>
              <span className="flex items-center gap-1">
                <Info className="w-3 h-3" />
                {data.notice}
              </span>
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
                    isSaving={saving === field.source}
                    onSave={(value) => void save(field, value)}
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
  isSaving,
  onSave,
}: {
  field: FormField;
  isSaving: boolean;
  onSave: (value: string) => void;
}) {
  const [isEditing, setIsEditing] = useState(false);
  const [draft, setDraft] = useState(field.value ?? "");

  const canEdit = field.editable && field.fill !== "classes";

  return (
    <div
      className={cn(
        "flex items-start gap-3 px-3 py-2",
        field.is_filled && "bg-emerald-500/5",
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
          {field.fill !== "auto" && (
            <span className="text-[10px] text-muted-foreground">
              {FILL_LABELS[field.fill] ?? field.fill}
            </span>
          )}
          {field.is_filled && (
            <Check className="w-3.5 h-3.5 text-emerald-600 shrink-0" />
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
              disabled={isSaving || !draft.trim()}
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
                  : "border-border text-muted-foreground",
              )}
            >
              {field.value ?? "не заполнено"}
            </p>
            {canEdit && (
              <Button
                size="sm"
                variant="ghost"
                className="h-7 text-[11px] shrink-0"
                onClick={() => setIsEditing(true)}
                data-testid={`edit-${field.source ?? field.label}`}
              >
                <Pencil className="w-3 h-3 mr-1" />
                {field.is_filled ? "Изменить" : "Заполнить"}
              </Button>
            )}
          </div>
        )}

        {field.hint && (
          <p className="text-[10px] text-muted-foreground">{field.hint}</p>
        )}
      </div>
    </div>
  );
}
