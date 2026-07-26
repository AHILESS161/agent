/**
 * Правовой анализ — единое место для всех проверок по делу.
 *
 * Раньше классы МКТУ, абсолютные основания и конфликты были разными
 * вкладками, хотя это части одной проверки: охраноспособность
 * оценивается не сама по себе, а в отношении конкретных товаров.
 * Поэтому анализ запускается одной кнопкой и идёт в жёстком порядке
 * (классы → абсолютные основания → конфликты), а вердикт выносится
 * по совокупности.
 *
 * Цвет здесь несёт смысл, а не украшает: зелёный — препятствий нет,
 * красный — основание для отказа. Решение специалиста («согласен» /
 * «не согласен») тоже окрашивается, чтобы на длинном списке было
 * видно, что уже отработано.
 */

import { useEffect, useState } from "react";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { useToast } from "@/hooks/use-toast";
import { AiDisclaimer, DemoModeBadge } from "@/components/ai-disclaimer";
import { api, ApiError } from "@/lib/api";
import { useApi, type ClassesDto, type ConflictsDto } from "@/lib/use-api";
import { cn } from "@/lib/utils";
import {
  AlertTriangle,
  Check,
  CheckCircle2,
  ChevronDown,
  Gavel,
  Layers,
  Loader2,
  Play,
  Plus,
  Search,
  Trash2,
  Shield,
  ShieldAlert,
  X,
  XCircle,
} from "lucide-react";

// --- вердикт ---------------------------------------------------------------

interface VerdictDto {
  overall_risk: string | null;
  verdict: string;
  verdict_text: string;
  classes_considered: number[];
  classes_confirmed: boolean;
  steps: { step: string; status: string; detail: string | null }[];
  incomplete_checks: string[];
  is_complete: boolean;
  limitations: string[];
}

const VERDICT_STYLES: Record<string, string> = {
  proceed: "border-emerald-500/50 bg-emerald-500/10",
  proceed_with_caution: "border-amber-500/50 bg-amber-500/10",
  revise: "border-orange-500/50 bg-orange-500/10",
  do_not_proceed: "border-red-500/50 bg-red-500/10",
  inconclusive: "border-slate-400/50 bg-slate-500/10",
};

const VERDICT_TITLES: Record<string, string> = {
  proceed: "Можно подавать",
  proceed_with_caution: "Можно подавать с оговорками",
  revise: "Требуется доработка",
  do_not_proceed: "Подача не рекомендуется",
  inconclusive: "Вывод не сформирован",
};

const VERDICT_ICONS: Record<string, typeof Shield> = {
  proceed: CheckCircle2,
  proceed_with_caution: AlertTriangle,
  revise: ShieldAlert,
  do_not_proceed: XCircle,
  inconclusive: Shield,
};

const VERDICT_TEXT_COLOR: Record<string, string> = {
  proceed: "text-emerald-700 dark:text-emerald-400",
  proceed_with_caution: "text-amber-700 dark:text-amber-500",
  revise: "text-orange-700 dark:text-orange-400",
  do_not_proceed: "text-red-700 dark:text-red-400",
  inconclusive: "text-muted-foreground",
};

const RISK_LABELS: Record<string, string> = {
  low: "Низкий риск",
  medium: "Средний риск",
  high: "Высокий риск",
  critical: "Критический риск",
};

// Цвет уровня риска у отдельного вывода.
const LEVEL_BORDER: Record<string, string> = {
  low: "border-l-emerald-500",
  medium: "border-l-amber-500",
  high: "border-l-orange-500",
  critical: "border-l-red-500",
};

const LEVEL_BADGE: Record<string, string> = {
  low: "bg-emerald-500/15 text-emerald-700 dark:text-emerald-400",
  medium: "bg-amber-500/15 text-amber-700 dark:text-amber-500",
  high: "bg-orange-500/15 text-orange-700 dark:text-orange-400",
  critical: "bg-red-500/15 text-red-700 dark:text-red-400",
};

const STEP_LABELS: Record<string, string> = {
  classes: "Классы МКТУ",
  absolute_grounds: "Абсолютные основания (п. 1–5)",
  relative_grounds: "Относительные основания (п. 6)",
};

interface FindingDto {
  id: number;
  category: string;
  level: string;
  legal_basis: string | null;
  explanation: string;
  recommendation?: string | null;
  recommended_action: string | null;
  confidence: number | null;
  reviewer_decision: string | null;
  citations: {
    id: number;
    quote: string;
    anchor: string | null;
    source_ref: string | null;
    status: string;
    is_trustworthy: boolean;
  }[];
  verification?: { semantic_verdict?: { llm_used?: boolean } };
}

interface ReportDto {
  overall_risk: string | null;
  sections: Record<
    string,
    {
      overall_risk: string | null;
      summary: string | null;
      is_inconclusive: boolean;
      inconclusive_reason: string | null;
      findings: FindingDto[];
      limitations: string[];
      provenance: { model_name: string | null; llm_used: boolean };
    } | null
  >;
}

export function LegalAnalysisTab({ appId }: { appId: number }) {
  const { toast } = useToast();
  const report = useApi<ReportDto>(`/applications/${appId}/risk-report`);
  const classes = useApi<ClassesDto>(`/applications/${appId}/classes`);
  const conflicts = useApi<ConflictsDto>(`/applications/${appId}/conflicts`);

  const [verdict, setVerdict] = useState<VerdictDto | null>(null);
  const [isRunning, setIsRunning] = useState(false);
  const [busyFinding, setBusyFinding] = useState<number | null>(null);

  const runAll = async () => {
    setIsRunning(true);
    try {
      const result = await api.post<VerdictDto>(
        `/applications/${appId}/full-analysis`,
      );
      setVerdict(result);
      toast({
        title: VERDICT_TITLES[result.verdict] ?? "Анализ выполнен",
        description: result.verdict_text,
        variant: result.verdict === "do_not_proceed" ? "destructive" : undefined,
      });
      report.reload();
      classes.reload();
      conflicts.reload();
    } catch (e) {
      toast({
        title: "Анализ не выполнен",
        description: e instanceof ApiError ? e.message : "Неизвестная ошибка",
        variant: "destructive",
      });
    } finally {
      setIsRunning(false);
    }
  };

  const review = async (findingId: number, decision: string) => {
    setBusyFinding(findingId);
    try {
      await api.post(`/risk-findings/${findingId}/review`, { decision });
      report.reload();
    } catch (e) {
      toast({
        title: "Не удалось сохранить решение",
        description: e instanceof ApiError ? e.message : "Неизвестная ошибка",
        variant: "destructive",
      });
    } finally {
      setBusyFinding(null);
    }
  };

  const absolute = report.data?.sections?.absolute_grounds ?? null;
  const relative = report.data?.sections?.relative_grounds ?? null;
  const overallRisk = verdict?.overall_risk ?? report.data?.overall_risk ?? null;

  // Вердикт после прогона показываем сразу; иначе выводим по сохранённому
  // отчёту, чтобы вкладка не выглядела пустой при возврате в дело.
  const verdictCode =
    verdict?.verdict ??
    (overallRisk
      ? { low: "proceed", medium: "proceed_with_caution", high: "revise", critical: "do_not_proceed" }[
          overallRisk
        ] ?? "inconclusive"
      : null);

  const VerdictIcon = VERDICT_ICONS[verdictCode ?? "inconclusive"];

  return (
    <div className="space-y-3" data-testid="legal-analysis-tab">
      {/* --- вердикт --- */}
      <Card className={cn("border-2", VERDICT_STYLES[verdictCode ?? "inconclusive"])}>
        <CardContent className="p-4 space-y-3">
          <div className="flex items-start justify-between gap-3">
            <div className="flex items-start gap-3 min-w-0">
              <VerdictIcon
                className={cn(
                  "w-7 h-7 shrink-0 mt-0.5",
                  VERDICT_TEXT_COLOR[verdictCode ?? "inconclusive"],
                )}
              />
              <div className="min-w-0">
                <h3
                  className={cn(
                    "text-base font-bold",
                    VERDICT_TEXT_COLOR[verdictCode ?? "inconclusive"],
                  )}
                  data-testid="verdict-title"
                >
                  {verdictCode
                    ? VERDICT_TITLES[verdictCode]
                    : "Анализ не проводился"}
                </h3>
                <p className="text-xs mt-0.5">
                  {verdict?.verdict_text ??
                    (verdictCode
                      ? "Вердикт по сохранённым результатам проверок."
                      : "Запустите полный анализ: классы МКТУ, абсолютные основания и конфликты.")}
                </p>
              </div>
            </div>
            <Button
              size="sm"
              disabled={isRunning}
              onClick={() => void runAll()}
              data-testid="run-full-analysis"
            >
              {isRunning ? (
                <Loader2 className="w-3.5 h-3.5 mr-1.5 animate-spin" />
              ) : (
                <Play className="w-3.5 h-3.5 mr-1.5" />
              )}
              {isRunning ? "Анализ…" : "Полный анализ"}
            </Button>
          </div>

          <div className="flex flex-wrap items-center gap-2">
            {overallRisk && (
              <Badge className={cn("text-[10px]", LEVEL_BADGE[overallRisk])}>
                {RISK_LABELS[overallRisk] ?? overallRisk}
              </Badge>
            )}
            {(verdict?.classes_considered?.length ?? 0) > 0 && (
              <Badge variant="secondary" className="text-[10px]">
                классы: {verdict!.classes_considered.join(", ")}
                {verdict!.classes_confirmed ? " · подтверждены" : " · не подтверждены"}
              </Badge>
            )}
            <DemoModeBadge label="Ограниченный demo-поиск" />
          </div>

          {isRunning && (
            <p className="text-[11px] text-muted-foreground">
              Выполняются проверки по порядку: классы → абсолютные основания →
              конфликты. Это занимает до минуты.
            </p>
          )}

          {/* Незавершённые проверки не должны выглядеть как «всё чисто». */}
          {verdict && verdict.incomplete_checks.length > 0 && (
            <div className="rounded-md border border-amber-500/40 bg-amber-500/5 px-3 py-2">
              <p className="text-[11px] font-medium mb-0.5">
                Проверки выполнены не полностью:
              </p>
              {verdict.incomplete_checks.map((item, i) => (
                <p key={i} className="text-[11px] text-muted-foreground">
                  • {item}
                </p>
              ))}
            </div>
          )}

          {verdict && verdict.steps.length > 0 && (
            <div className="flex flex-wrap gap-2">
              {verdict.steps.map((step) => (
                <span
                  key={step.step}
                  className={cn(
                    "text-[10px] px-2 py-0.5 rounded-full border",
                    step.status === "ok"
                      ? "border-emerald-500/40 text-emerald-700 dark:text-emerald-400"
                      : step.status === "skipped"
                        ? "border-border text-muted-foreground"
                        : "border-amber-500/40 text-amber-700 dark:text-amber-500",
                  )}
                  title={step.detail ?? undefined}
                >
                  {STEP_LABELS[step.step] ?? step.step}
                  {step.status === "ok"
                    ? " ✓"
                    : step.status === "skipped"
                      ? " —"
                      : " !"}
                </span>
              ))}
            </div>
          )}
        </CardContent>
      </Card>

      <AiDisclaimer />

      {/* --- классы МКТУ --- */}
      <Section
        icon={Layers}
        title="Классы МКТУ"
        hint="От перечня классов зависит вывод об охраноспособности: обозначение бывает описательным для одних товаров и фантазийным для других."
      >
        <ClassList appId={appId} state={classes} />
      </Section>

      {/* --- абсолютные основания --- */}
      <Section
        icon={Shield}
        title="Абсолютные основания (ст. 1483 п. 1–5)"
        hint="Каждый вывод обязан ссылаться на норму, и ссылка проверяется дословно: вывод без подтверждённой цитаты отбрасывается."
        badge={
          absolute?.findings?.length ? String(absolute.findings.length) : undefined
        }
      >
        {absolute?.is_inconclusive && (
          <InconclusiveNote reason={absolute.inconclusive_reason} />
        )}
        {absolute?.summary && (
          <p className="text-xs leading-relaxed mb-2">{absolute.summary}</p>
        )}
        {absolute?.findings?.length ? (
          <div className="space-y-2">
            {absolute.findings.map((finding) => (
              <FindingCard
                key={finding.id}
                finding={finding}
                isBusy={busyFinding === finding.id}
                onReview={(d) => void review(finding.id, d)}
              />
            ))}
          </div>
        ) : (
          !absolute?.is_inconclusive && (
            <p className="text-xs text-muted-foreground">
              {absolute
                ? "Оснований для отказа не выявлено."
                : "Проверка не проводилась."}
            </p>
          )
        )}
      </Section>

      {/* --- относительные основания --- */}
      <Section
        icon={Search}
        title="Относительные основания (ст. 1483 п. 6)"
        hint="Сходство до степени смешения с чужими знаками по критериям п. 42 Правил № 482 и п. 162 Пленума ВС РФ № 10."
        badge={
          relative?.findings?.length ? String(relative.findings.length) : undefined
        }
      >
        {relative?.is_inconclusive && (
          <InconclusiveNote reason={relative.inconclusive_reason} />
        )}
        {relative?.summary && (
          <p className="text-xs leading-relaxed mb-2">{relative.summary}</p>
        )}
        {relative?.findings?.length ? (
          <div className="space-y-2">
            {relative.findings.map((finding) => (
              <FindingCard
                key={finding.id}
                finding={finding}
                isBusy={busyFinding === finding.id}
                onReview={(d) => void review(finding.id, d)}
              />
            ))}
          </div>
        ) : (
          !relative?.is_inconclusive && (
            <p className="text-xs text-muted-foreground">
              {relative
                ? "Конфликтующих обозначений не обнаружено."
                : "Поиск не проводился."}
            </p>
          )
        )}
      </Section>

      {/* --- итоговое заключение --- */}
      <MemoSection appId={appId} />

      {/* --- ограничения --- */}
      {((verdict?.limitations?.length ?? 0) > 0 ||
        (absolute?.limitations?.length ?? 0) > 0 ||
        (relative?.limitations?.length ?? 0) > 0) && (
        <details className="rounded-lg border border-border p-3">
          <summary className="text-xs font-medium cursor-pointer flex items-center gap-1.5">
            <AlertTriangle className="w-3.5 h-3.5 text-amber-600" />
            Ограничения анализа
          </summary>
          <div className="mt-2 space-y-1">
            {Array.from(
              new Set([
                ...(verdict?.limitations ?? []),
                ...(absolute?.limitations ?? []),
                ...(relative?.limitations ?? []),
              ]),
            ).map((item, i) => (
              <p key={i} className="text-[11px] text-muted-foreground">
                • {item}
              </p>
            ))}
          </div>
        </details>
      )}
    </div>
  );
}

/**
 * Перечень классов МКТУ с решением специалиста.
 *
 * Класс, предложенный системой, — это предложение: пока специалист
 * его не подтвердил, он не попадает в заявление. Поэтому решение
 * принимается прямо здесь, а не на отдельном экране. Своего класса
 * в предложениях может не оказаться — его можно добавить вручную.
 */
function ClassList({
  appId,
  state,
}: {
  appId: number;
  state: ReturnType<typeof useApi<ClassesDto>>;
}) {
  const { toast } = useToast();
  const [busy, setBusy] = useState<number | null>(null);
  const [isAdding, setIsAdding] = useState(false);

  const fail = (e: unknown, title: string) =>
    toast({
      title,
      description: e instanceof ApiError ? e.message : "Неизвестная ошибка",
      variant: "destructive",
    });

  const decide = async (classId: number, approved: boolean) => {
    setBusy(classId);
    try {
      await api.put(`/applications/${appId}/classes/${classId}/approve`, {
        suggestion_id: classId,
        approved,
      });
      state.reload();
    } catch (e) {
      fail(e, "Не удалось сохранить решение");
    } finally {
      setBusy(null);
    }
  };

  const remove = async (classId: number) => {
    setBusy(classId);
    try {
      await api.delete(`/applications/${appId}/classes/${classId}`);
      state.reload();
    } catch (e) {
      fail(e, "Не удалось удалить класс");
    } finally {
      setBusy(null);
    }
  };

  const add = async (number: number, description: string) => {
    setBusy(-1);
    try {
      await api.post(`/applications/${appId}/classes`, {
        class_number: number,
        class_description: description || null,
      });
      setIsAdding(false);
      state.reload();
    } catch (e) {
      fail(e, "Не удалось добавить класс");
    } finally {
      setBusy(null);
    }
  };

  const items = state.data?.suggestions ?? [];

  return (
    <div className="space-y-1.5">
      {items.length === 0 && (
        <p className="text-xs text-muted-foreground">
          Классы не определены. Они подбираются на первом шаге полного анализа
          либо добавляются вручную.
        </p>
      )}

      {items.map((item) => {
        const approved = item.approved === true;
        const rejected = item.approved === false;
        return (
          <div
            key={item.id}
            className={cn(
              "flex flex-wrap items-center gap-2 rounded-md border px-2.5 py-1.5",
              approved && "border-emerald-500/40 bg-emerald-500/5",
              rejected && "border-red-500/40 bg-red-500/5 opacity-70",
              !approved && !rejected && "border-border",
            )}
            data-testid={`class-${item.id}`}
          >
            <Badge className="text-[10px]">Класс {item.class_number}</Badge>
            {approved && (
              <Badge className="bg-emerald-500/15 text-emerald-700 dark:text-emerald-400 text-[10px]">
                подтверждён
              </Badge>
            )}
            {rejected && (
              <Badge className="bg-red-500/15 text-red-700 dark:text-red-400 text-[10px]">
                отклонён
              </Badge>
            )}
            {!approved && !rejected && (
              <Badge variant="outline" className="text-[10px]">
                не подтверждён
              </Badge>
            )}
            <span className="text-[11px] text-muted-foreground min-w-0 flex-1">
              {item.class_description || item.rationale}
            </span>

            <div className="flex items-center gap-1 shrink-0">
              <button
                type="button"
                title="Подтвердить класс"
                disabled={busy === item.id}
                onClick={() => void decide(item.id, true)}
                className={cn(
                  "p-1 rounded hover:bg-emerald-500/15",
                  approved ? "text-emerald-600" : "text-muted-foreground",
                )}
                data-testid={`approve-class-${item.id}`}
              >
                <Check className="w-4 h-4" />
              </button>
              <button
                type="button"
                title="Отклонить класс"
                disabled={busy === item.id}
                onClick={() => void decide(item.id, false)}
                className={cn(
                  "p-1 rounded hover:bg-red-500/15",
                  rejected ? "text-red-600" : "text-muted-foreground",
                )}
                data-testid={`reject-class-${item.id}`}
              >
                <X className="w-4 h-4" />
              </button>
              <button
                type="button"
                title="Удалить класс из дела"
                disabled={busy === item.id}
                onClick={() => void remove(item.id)}
                className="p-1 rounded hover:bg-destructive/15 text-muted-foreground"
                data-testid={`delete-class-${item.id}`}
              >
                <Trash2 className="w-3.5 h-3.5" />
              </button>
            </div>
          </div>
        );
      })}

      {isAdding ? (
        <ClassPicker
          taken={items.map((i) => i.class_number)}
          isBusy={busy === -1}
          onCancel={() => setIsAdding(false)}
          onPick={(number, description) => void add(number, description)}
        />
      ) : (
        <Button
          size="sm"
          variant="outline"
          className="h-7 text-[11px]"
          onClick={() => setIsAdding(true)}
          data-testid="add-class"
        >
          <Plus className="w-3.5 h-3.5 mr-1" />
          Добавить класс
        </Button>
      )}
    </div>
  );
}

interface CatalogItem {
  class_number: number;
  title: string;
  description: string;
  kind: string;
}

/**
 * Поиск класса МКТУ по смыслу.
 *
 * Держать в голове номера всех 45 классов невозможно, поэтому класс
 * ищется словами — «одежда», «кофе», «разработка ПО». Номер тоже
 * работает: специалист, который его помнит, не должен искать вслепую.
 * Уже добавленные классы показываются, но выбрать их нельзя.
 */
function ClassPicker({
  taken,
  isBusy,
  onPick,
  onCancel,
}: {
  taken: number[];
  isBusy: boolean;
  onPick: (number: number, description: string) => void;
  onCancel: () => void;
}) {
  const [query, setQuery] = useState("");
  const [items, setItems] = useState<CatalogItem[]>([]);
  const [isSearching, setIsSearching] = useState(false);

  // Запрос идёт с задержкой: справочник маленький, но дёргать API
  // на каждую букву незачем.
  useEffect(() => {
    let cancelled = false;
    setIsSearching(true);
    const timer = setTimeout(() => {
      api
        .get<{ items: CatalogItem[] }>(
          `/nice-classes/catalog?q=${encodeURIComponent(query)}&limit=8`,
        )
        .then((data) => {
          if (!cancelled) setItems(data.items);
        })
        .catch(() => {
          if (!cancelled) setItems([]);
        })
        .finally(() => {
          if (!cancelled) setIsSearching(false);
        });
    }, 200);
    return () => {
      cancelled = true;
      clearTimeout(timer);
    };
  }, [query]);

  return (
    <div className="rounded-md border border-dashed border-border p-2 space-y-2">
      <div className="flex items-center gap-2">
        <Search className="w-3.5 h-3.5 text-muted-foreground shrink-0" />
        <Input
          autoFocus
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          placeholder="Найти класс: одежда, кофе, разработка ПО, 25…"
          className="h-7 text-xs"
          data-testid="class-search"
        />
        <Button
          size="sm"
          variant="ghost"
          className="h-7 text-[11px] shrink-0"
          onClick={onCancel}
        >
          Отмена
        </Button>
      </div>

      <div className="max-h-64 overflow-y-auto space-y-1">
        {isSearching && items.length === 0 && (
          <p className="text-[11px] text-muted-foreground px-1">Поиск…</p>
        )}
        {!isSearching && items.length === 0 && (
          <p className="text-[11px] text-muted-foreground px-1">
            Ничего не найдено. Попробуйте другое слово или номер класса.
          </p>
        )}
        {items.map((item) => {
          const already = taken.includes(item.class_number);
          return (
            <button
              key={item.class_number}
              type="button"
              disabled={already || isBusy}
              onClick={() => onPick(item.class_number, item.description)}
              className={cn(
                "w-full text-left rounded-md border px-2.5 py-1.5 transition-colors",
                already
                  ? "border-border opacity-50 cursor-not-allowed"
                  : "border-border hover:border-primary hover:bg-primary/5",
              )}
              data-testid={`pick-class-${item.class_number}`}
            >
              <div className="flex flex-wrap items-center gap-2">
                <Badge className="text-[10px]">Класс {item.class_number}</Badge>
                <span className="text-xs font-medium">{item.title}</span>
                <span className="text-[10px] text-muted-foreground">
                  {item.kind}
                </span>
                {already && (
                  <span className="text-[10px] text-muted-foreground ml-auto">
                    уже добавлен
                  </span>
                )}
              </div>
              <p className="text-[11px] text-muted-foreground mt-0.5 line-clamp-2">
                {item.description}
              </p>
            </button>
          );
        })}
      </div>
    </div>
  );
}

/**
 * Итоговое заключение по делу.
 *
 * Раньше жило отдельной вкладкой «Рекомендации», хотя это результат
 * того же анализа: смотреть вывод отдельно от оснований, на которых
 * он построен, неудобно и опасно.
 */
function MemoSection({ appId }: { appId: number }) {
  const state = useApi<{
    summary: string | null;
    risk_assessment: string | null;
    recommended_action: string | null;
    recommended_classes_json: number[] | null;
    key_risks_json: string[] | null;
    confidence: number | null;
    approved_by: number | null;
  }>(`/applications/${appId}/recommendation`);

  const memo = state.data;
  if (!memo) return null;

  const ACTIONS: Record<string, string> = {
    proceed: "Подавать заявку",
    modify: "Доработать обозначение или перечень",
    withdraw: "Не подавать в текущем виде",
    further_review: "Требуется дополнительная проверка",
  };

  return (
    <Section
      icon={Gavel}
      title="Итоговое заключение"
      hint="Собрано по результатам проверок. Требует подтверждения специалистом."
    >
      <div className="space-y-2">
        {memo.recommended_action && (
          <div className="flex flex-wrap items-center gap-2">
            <span className="text-xs font-medium">Рекомендуемое действие:</span>
            <Badge className="text-[10px]">
              {ACTIONS[memo.recommended_action] ?? memo.recommended_action}
            </Badge>
            {memo.confidence == null && (
              <span className="text-[10px] text-muted-foreground">
                уверенность не определена: проверки выполнены не полностью
              </span>
            )}
          </div>
        )}

        {memo.summary && <p className="text-xs leading-relaxed">{memo.summary}</p>}

        {memo.risk_assessment && (
          <p className="text-[11px] text-muted-foreground leading-relaxed">
            {memo.risk_assessment}
          </p>
        )}

        {(memo.recommended_classes_json?.length ?? 0) > 0 && (
          <p className="text-[11px]">
            <span className="text-muted-foreground">Классы:</span>{" "}
            {memo.recommended_classes_json!.join(", ")}
          </p>
        )}

        {(memo.key_risks_json?.length ?? 0) > 0 && (
          <details className="text-[11px]">
            <summary className="cursor-pointer text-muted-foreground">
              Ключевые риски ({memo.key_risks_json!.length})
            </summary>
            <ul className="mt-1 space-y-0.5 pl-3">
              {memo.key_risks_json!.map((risk, index) => (
                <li key={index}>• {risk}</li>
              ))}
            </ul>
          </details>
        )}
      </div>
    </Section>
  );
}

function InconclusiveNote({ reason }: { reason: string | null }) {
  return (
    <div className="flex items-start gap-2 rounded-md border border-amber-500/40 bg-amber-500/10 px-3 py-2 mb-2">
      <AlertTriangle className="w-4 h-4 shrink-0 mt-0.5 text-amber-600" />
      <p className="text-xs">
        {reason ?? "Недостаточно подтверждённых данных для вывода."}
      </p>
    </div>
  );
}

function Section({
  icon: Icon,
  title,
  hint,
  badge,
  children,
}: {
  icon: typeof Shield;
  title: string;
  hint?: string;
  badge?: string;
  children: React.ReactNode;
}) {
  const [open, setOpen] = useState(true);
  return (
    <Card>
      <CardContent className="p-3">
        <button
          type="button"
          className="flex items-center gap-2 w-full text-left"
          onClick={() => setOpen((v) => !v)}
        >
          <Icon className="w-4 h-4 text-muted-foreground shrink-0" />
          <span className="text-sm font-semibold">{title}</span>
          {badge && (
            <Badge variant="secondary" className="text-[10px]">
              {badge}
            </Badge>
          )}
          <ChevronDown
            className={cn(
              "w-4 h-4 ml-auto text-muted-foreground transition-transform",
              !open && "-rotate-90",
            )}
          />
        </button>
        {open && (
          <div className="mt-2">
            {hint && (
              <p className="text-[11px] text-muted-foreground mb-2">{hint}</p>
            )}
            {children}
          </div>
        )}
      </CardContent>
    </Card>
  );
}

/**
 * Карточка вывода.
 *
 * Слева — цветная полоса по уровню риска, чтобы серьёзность читалась
 * до чтения текста. Решение специалиста подсвечивает всю карточку:
 * зелёным, если он согласен, красным — если отклонил.
 */
function FindingCard({
  finding,
  isBusy,
  onReview,
}: {
  finding: FindingDto;
  isBusy: boolean;
  onReview: (decision: string) => void;
}) {
  const decision = finding.reviewer_decision;
  const agreed = decision === "approve";
  const rejected = decision === "reject";

  return (
    <div
      className={cn(
        "rounded-md border border-l-4 p-3 space-y-2",
        LEVEL_BORDER[finding.level] ?? "border-l-slate-400",
        agreed && "bg-emerald-500/5 border-emerald-500/40",
        rejected && "bg-red-500/5 border-red-500/40 opacity-70",
        !decision && "border-border",
      )}
      data-testid={`finding-${finding.id}`}
    >
      <div className="flex flex-wrap items-center gap-2">
        <Badge className={cn("text-[10px]", LEVEL_BADGE[finding.level])}>
          {RISK_LABELS[finding.level] ?? finding.level}
        </Badge>
        {finding.legal_basis && (
          <span className="text-[11px] font-mono">{finding.legal_basis}</span>
        )}
        {finding.verification?.semantic_verdict?.llm_used && (
          <Badge variant="outline" className="text-[10px] border-amber-500/50">
            смысл определён моделью
          </Badge>
        )}
        {agreed && (
          <Badge className="bg-emerald-500/15 text-emerald-700 dark:text-emerald-400 text-[10px] ml-auto">
            <Check className="w-3 h-3 mr-1" />
            согласен
          </Badge>
        )}
        {rejected && (
          <Badge className="bg-red-500/15 text-red-700 dark:text-red-400 text-[10px] ml-auto">
            <X className="w-3 h-3 mr-1" />
            не согласен
          </Badge>
        )}
      </div>

      <p className="text-xs leading-relaxed">{finding.explanation}</p>

      {finding.citations.map((citation) => (
        <div
          key={citation.id}
          className={cn(
            "rounded border px-2 py-1.5",
            citation.is_trustworthy
              ? "border-border"
              : "border-destructive/40 bg-destructive/5",
          )}
        >
          <span className="text-[10px] font-mono text-muted-foreground">
            {citation.anchor ?? citation.source_ref ?? "источник"}
          </span>
          <p className="text-[11px] italic mt-0.5">«{citation.quote}»</p>
        </div>
      ))}

      {finding.recommended_action && (
        <p className="text-[11px]">
          <span className="font-medium">Рекомендация:</span>{" "}
          {finding.recommended_action}
        </p>
      )}

      <div className="flex flex-wrap gap-2 pt-0.5">
        <Button
          size="sm"
          variant={agreed ? "default" : "outline"}
          className={cn(
            "h-7 text-[11px]",
            agreed && "bg-emerald-600 hover:bg-emerald-700 text-white",
          )}
          disabled={isBusy}
          onClick={() => onReview("approve")}
          data-testid={`agree-${finding.id}`}
        >
          <Check className="w-3 h-3 mr-1" />
          Согласен
        </Button>
        <Button
          size="sm"
          variant={rejected ? "default" : "outline"}
          className={cn(
            "h-7 text-[11px]",
            rejected && "bg-red-600 hover:bg-red-700 text-white",
          )}
          disabled={isBusy}
          onClick={() => onReview("reject")}
          data-testid={`reject-${finding.id}`}
        >
          <X className="w-3 h-3 mr-1" />
          Не согласен
        </Button>
        <Button
          size="sm"
          variant="ghost"
          className="h-7 text-[11px]"
          disabled={isBusy}
          onClick={() => onReview("modify")}
        >
          Требует доработки
        </Button>
      </div>
    </div>
  );
}
