/**
 * Черновик заявления: предзаполнение бланка подтверждёнными данными.
 *
 * Главное, что должен видеть специалист, — не только то, что попало
 * в документ, но и то, что осталось пустым и почему. Поле без
 * подтверждения не заполняется, даже если система в нём уверена,
 * поэтому список пропусков здесь такая же часть результата, как
 * и список заполненных значений.
 */

import { useState } from "react";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { useToast } from "@/hooks/use-toast";
import { AsyncSection } from "@/components/async-states";
import { AiDisclaimer } from "@/components/ai-disclaimer";
import { api, ApiError } from "@/lib/api";
import { useApi } from "@/lib/use-api";
import { cn } from "@/lib/utils";
import { Check, Download, FileSignature, Loader2, Trash2 } from "lucide-react";
import { DraftFormView } from "@/components/draft-form-view";

interface FilledField {
  field_id: string;
  label: string;
  value: string;
  source: string;
}

interface SkippedField {
  field_id: string;
  label: string;
  reason: string;
}

interface DraftDto {
  id: number;
  version: number;
  status: string;
  filled_fields: FilledField[];
  skipped_fields: SkippedField[];
  checklist: string[];
  can_export: boolean;
  provenance: {
    template_name: string | null;
    schema_version: string | null;
    mapping_version: number | null;
  };
}

const STATUS_LABELS: Record<string, string> = {
  draft: "Черновик",
  ready_for_review: "На проверке",
  approved_by_specialist: "Утверждён специалистом",
  exported: "Выгружен",
};

const STATUS_STYLES: Record<string, string> = {
  draft: "bg-slate-500/15 text-slate-700 dark:text-slate-300",
  ready_for_review: "bg-amber-500/15 text-amber-700 dark:text-amber-500",
  approved_by_specialist:
    "bg-emerald-500/15 text-emerald-700 dark:text-emerald-400",
  exported: "bg-blue-500/15 text-blue-700 dark:text-blue-400",
};

export function ApplicationDraftTab({ appId }: { appId: number }) {
  const { toast } = useToast();
  const state = useApi<{ items: DraftDto[]; total: number }>(
    `/applications/${appId}/drafts`,
  );
  const [busyId, setBusyId] = useState<number | "new" | null>(null);

  const describeError = (e: unknown) =>
    e instanceof ApiError ? e.message : "Неизвестная ошибка";

  const generate = async () => {
    setBusyId("new");
    try {
      const draft = await api.post<DraftDto>(`/applications/${appId}/draft`);
      toast({
        title: `Черновик сформирован (версия ${draft.version})`,
        description:
          `Заполнено полей: ${draft.filled_fields.length}, ` +
          `оставлено пустыми: ${draft.skipped_fields.length}.`,
      });
      state.reload();
    } catch (e) {
      toast({
        title: "Не удалось сформировать черновик",
        description: describeError(e),
        variant: "destructive",
      });
    } finally {
      setBusyId(null);
    }
  };

  const approve = async (draftId: number) => {
    setBusyId(draftId);
    try {
      await api.post(`/drafts/${draftId}/approve`);
      toast({
        title: "Черновик утверждён",
        description: "Теперь документ можно выгрузить.",
      });
      state.reload();
    } catch (e) {
      toast({
        title: "Не удалось утвердить черновик",
        description: describeError(e),
        variant: "destructive",
      });
    } finally {
      setBusyId(null);
    }
  };

  const remove = async (draft: DraftDto) => {
    if (
      !window.confirm(
        `Удалить версию ${draft.version}? Файл черновика будет удалён.`,
      )
    ) {
      return;
    }
    setBusyId(draft.id);
    try {
      await api.delete(`/drafts/${draft.id}`);
      toast({ title: `Версия ${draft.version} удалена` });
      state.reload();
    } catch (e) {
      toast({
        title: "Не удалось удалить версию",
        description: describeError(e),
        variant: "destructive",
      });
    } finally {
      setBusyId(null);
    }
  };

  const download = async (draft: DraftDto) => {
    try {
      await api.download(
        `/drafts/${draft.id}/download`,
        `zayavka-delo-${appId}-v${draft.version}.docx`,
      );
      state.reload();
    } catch (e) {
      toast({
        title: "Не удалось скачать черновик",
        description: describeError(e),
        variant: "destructive",
      });
    }
  };

  return (
    <div className="space-y-3">
      <div className="flex flex-col sm:flex-row sm:items-start justify-between gap-2">
        <p className="text-xs text-muted-foreground max-w-lg">
          Бланк заполняется только значениями, подтверждёнными на этапе
          «Данные». Поля с конфликтом, требующие проверки или не
          найденные в документах, остаются пустыми — причина указана ниже.
          Выгрузка доступна после утверждения специалистом.
        </p>
        <Button
          size="sm"
          disabled={busyId !== null}
          onClick={() => void generate()}
          data-testid="generate-draft"
        >
          {busyId === "new" ? (
            <Loader2 className="w-3.5 h-3.5 mr-1.5 animate-spin" />
          ) : (
            <FileSignature className="w-3.5 h-3.5 mr-1.5" />
          )}
          Сформировать черновик
        </Button>
      </div>

      {/* Сам бланк: специалист видит заявление в структуре формы
          Роспатента и дозаполняет поля прямо здесь. */}
      <DraftFormView appId={appId} />

      <AsyncSection
        state={state}
        loadingLabel="Загрузка черновиков…"
        emptyTitle="Черновик не формировался"
        emptyHint="Нажмите «Сформировать черновик», чтобы предзаполнить заявление подтверждёнными данными."
      >
        {(data) =>
          data.items.length === 0 ? (
            <p className="text-xs text-muted-foreground">
              Черновик ещё не формировался.
            </p>
          ) : (
            <div className="space-y-2">
              {data.items.map((draft) => (
                <DraftCard
                  key={draft.id}
                  draft={draft}
                  isBusy={busyId !== null}
                  onApprove={() => void approve(draft.id)}
                  onDownload={() => void download(draft)}
                  onDelete={() => void remove(draft)}
                />
              ))}
              <AiDisclaimer compact />
            </div>
          )
        }
      </AsyncSection>
    </div>
  );
}

function DraftCard({
  draft,
  isBusy,
  onApprove,
  onDownload,
  onDelete,
}: {
  draft: DraftDto;
  isBusy: boolean;
  onApprove: () => void;
  onDownload: () => void;
  onDelete: () => void;
}) {
  return (
    <Card data-testid={`draft-${draft.id}`}>
      <CardContent className="p-3 space-y-2">
        <div className="flex flex-wrap items-center gap-2">
          <span className="text-sm font-medium">Версия {draft.version}</span>
          <Badge className={cn("text-[10px]", STATUS_STYLES[draft.status])}>
            {STATUS_LABELS[draft.status] ?? draft.status}
          </Badge>
          <span className="text-[11px] text-muted-foreground">
            заполнено {draft.filled_fields.length} · оставлено пустыми{" "}
            {draft.skipped_fields.length}
          </span>
        </div>

        {draft.filled_fields.length > 0 && (
          <div className="rounded-md border border-border p-2 space-y-1">
            <p className="text-[11px] font-medium">Попадёт в заявление</p>
            {draft.filled_fields.map((item) => (
              <p key={item.field_id} className="text-[11px]">
                <span className="text-muted-foreground">{item.label}:</span>{" "}
                {item.value}{" "}
                <span className="text-muted-foreground">({item.source})</span>
              </p>
            ))}
          </div>
        )}

        {draft.skipped_fields.length > 0 && (
          <div className="rounded-md border border-amber-500/40 bg-amber-500/5 p-2 space-y-1">
            <p className="text-[11px] font-medium">
              Оставлено пустым намеренно
            </p>
            {draft.skipped_fields.map((item) => (
              <p key={item.field_id} className="text-[11px]">
                <span className="text-muted-foreground">{item.label}</span> —{" "}
                {item.reason}
              </p>
            ))}
          </div>
        )}

        {draft.checklist.length > 0 && (
          <details className="text-[11px]">
            <summary className="cursor-pointer text-muted-foreground">
              Заполнить вручную перед подачей ({draft.checklist.length})
            </summary>
            <ul className="mt-1 space-y-0.5 pl-3">
              {draft.checklist.map((item, index) => (
                <li key={index}>• {item}</li>
              ))}
            </ul>
          </details>
        )}

        <p className="text-[10px] text-muted-foreground">
          бланк: {draft.provenance.template_name ?? "—"} · схема{" "}
          {draft.provenance.schema_version ?? "—"} · маппинг v
          {draft.provenance.mapping_version ?? "—"}
        </p>

        <div className="flex flex-wrap gap-2 pt-1">
          {!draft.can_export && (
            <Button
              size="sm"
              variant="outline"
              disabled={isBusy}
              onClick={onApprove}
              data-testid={`approve-draft-${draft.id}`}
            >
              <Check className="w-3.5 h-3.5 mr-1.5" />
              Утвердить
            </Button>
          )}
          <Button
            size="sm"
            variant={draft.can_export ? "default" : "ghost"}
            disabled={!draft.can_export}
            onClick={onDownload}
            data-testid={`download-draft-${draft.id}`}
          >
            <Download className="w-3.5 h-3.5 mr-1.5" />
            {draft.can_export ? "Скачать DOCX" : "Скачать (нужно утвердить)"}
          </Button>

          {/* Выгруженную версию удалить нельзя: файл ушёл наружу,
              и след о нём должен остаться в деле. */}
          {draft.status !== "exported" && (
            <Button
              size="sm"
              variant="ghost"
              className="text-muted-foreground hover:text-destructive"
              disabled={isBusy}
              onClick={onDelete}
              data-testid={`delete-draft-${draft.id}`}
            >
              <Trash2 className="w-3.5 h-3.5 mr-1.5" />
              Удалить версию
            </Button>
          )}
        </div>
      </CardContent>
    </Card>
  );
}
