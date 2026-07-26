import { useState } from "react";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { useToast } from "@/hooks/use-toast";
import { AiDisclaimer } from "@/components/ai-disclaimer";
import { ErrorState, LoadingState, EmptyState } from "@/components/async-states";
import { api, ApiError } from "@/lib/api";
import { useApi } from "@/lib/use-api";
import { cn } from "@/lib/utils";
import { AlertTriangle, Check, Loader2, Play, ShieldQuestion, X } from "lucide-react";

const RISK_STYLES: Record<string, string> = {
  low: "bg-emerald-500/15 text-emerald-700 dark:text-emerald-400",
  medium: "bg-amber-500/15 text-amber-700 dark:text-amber-500",
  high: "bg-orange-500/15 text-orange-700 dark:text-orange-400",
  critical: "bg-red-500/15 text-red-700 dark:text-red-400",
};

const RISK_LABELS: Record<string, string> = {
  low: "Низкий",
  medium: "Средний",
  high: "Высокий",
  critical: "Критический",
};

const CITATION_STATUS_LABELS: Record<string, string> = {
  verified: "подтверждена",
  partial: "частично подтверждена",
  not_found: "не найдена в источнике",
  source_missing: "источник не существует",
  too_short: "слишком короткая",
};

interface CitationDto {
  id: number;
  source_ref: string | null;
  knowledge_chunk_id: number | null;
  quote: string;
  anchor: string | null;
  status: string;
  matched_ratio: number | null;
  is_trustworthy: boolean;
}

interface FindingDto {
  id: number;
  category: string;
  level: string;
  legal_basis: string | null;
  explanation: string;
  case_facts: string[];
  missing_data: string[];
  confidence: number | null;
  recommended_action: string | null;
  citations_verified: boolean;
  citations: CitationDto[];
  reviewer_decision: string | null;
  reviewer_comment: string | null;
}

interface AssessmentDto {
  id: number;
  overall_risk: string | null;
  summary: string | null;
  is_inconclusive: boolean;
  inconclusive_reason: string | null;
  limitations: string[];
  missing_data: string[];
  classes_considered: number[];
  classes_confirmed: boolean;
  provenance: {
    knowledge_base_version: string | null;
    model_name: string | null;
    llm_used: boolean;
    search_mode: string;
    sources_used: string[];
    verification: Record<string, unknown>;
  };
  findings: FindingDto[];
  created_at: string | null;
  disclaimer: string;
}

export function RiskAnalysisTab({ appId }: { appId: number }) {
  const { toast } = useToast();
  const state = useApi<{ assessment: AssessmentDto | null }>(
    `/applications/${appId}/risk-analysis`,
  );
  const [isRunning, setIsRunning] = useState(false);
  const [busyFinding, setBusyFinding] = useState<number | null>(null);

  const run = async () => {
    setIsRunning(true);
    try {
      const result = await api.post<AssessmentDto>(
        `/applications/${appId}/risk-analysis`,
      );
      toast({
        title: result.is_inconclusive ? "Вывод не сформирован" : "Анализ выполнен",
        description: result.is_inconclusive
          ? result.inconclusive_reason ?? undefined
          : `Установлено рисков: ${result.findings.length}`,
        variant: result.is_inconclusive ? "destructive" : undefined,
      });
      state.reload();
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
      toast({ title: "Решение сохранено" });
      state.reload();
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

  const header = (
    <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-2">
      <p className="text-xs text-muted-foreground max-w-lg">
        Оценка рисков по абсолютным основаниям (ст. 1483 ГК РФ). Каждый вывод
        обязан ссылаться на норму, и ссылка проверяется дословно: вывод без
        подтверждённой цитаты отбрасывается.
      </p>
      <Button size="sm" disabled={isRunning} onClick={() => void run()}>
        {isRunning ? (
          <Loader2 className="w-3.5 h-3.5 mr-1.5 animate-spin" />
        ) : (
          <Play className="w-3.5 h-3.5 mr-1.5" />
        )}
        {isRunning ? "Анализ…" : "Запустить анализ"}
      </Button>
    </div>
  );

  if (state.isLoading) return <LoadingState label="Загрузка оценки рисков…" />;
  if (state.error)
    return <ErrorState message={state.error} onRetry={state.reload} />;

  const assessment = state.data?.assessment ?? null;

  if (!assessment) {
    return (
      <div className="space-y-3">
        {header}
        <EmptyState
          title="Анализ рисков не проводился"
          hint="Запустите анализ, чтобы получить предварительную оценку с ссылками на нормы."
        />
      </div>
    );
  }

  return (
    <div className="space-y-3" data-testid="risk-analysis-tab">
      {header}
      <AiDisclaimer />

      <Card>
        <CardContent className="p-3 space-y-2">
          <div className="flex flex-wrap items-center gap-2">
            <span className="text-sm font-medium">Итоговый риск:</span>
            {assessment.overall_risk ? (
              <Badge
                className={cn("text-[10px]", RISK_STYLES[assessment.overall_risk])}
              >
                {RISK_LABELS[assessment.overall_risk] ?? assessment.overall_risk}
              </Badge>
            ) : (
              <Badge variant="outline" className="text-[10px]">
                вывод не сформирован
              </Badge>
            )}
            {assessment.classes_considered.length > 0 && (
              <Badge variant="secondary" className="text-[10px]">
                классы: {assessment.classes_considered.join(", ")}
                {assessment.classes_confirmed ? " (подтверждены)" : " (не подтверждены)"}
              </Badge>
            )}
          </div>

          {assessment.summary && (
            <p className="text-xs leading-relaxed">{assessment.summary}</p>
          )}

          {assessment.is_inconclusive && (
            <div className="flex items-start gap-2 rounded-md border border-amber-500/40 bg-amber-500/10 px-3 py-2">
              <ShieldQuestion className="w-4 h-4 shrink-0 mt-0.5 text-amber-600" />
              <p className="text-xs">
                {assessment.inconclusive_reason ??
                  "Недостаточно подтверждённых данных для вывода."}
              </p>
            </div>
          )}

          {/* Сведения для воспроизводимости вывода. */}
          <p className="text-[10px] text-muted-foreground">
            база знаний: {assessment.provenance.knowledge_base_version ?? "—"} ·
            модель: {assessment.provenance.model_name ?? "—"} · режим поиска:{" "}
            {assessment.provenance.search_mode} · источников:{" "}
            {assessment.provenance.sources_used.length}
            {assessment.created_at
              ? ` · ${new Date(assessment.created_at).toLocaleString("ru-RU")}`
              : ""}
          </p>
        </CardContent>
      </Card>

      {assessment.findings.map((finding) => (
        <Card key={finding.id}>
          <CardContent className="p-3 space-y-2">
            <div className="flex flex-wrap items-center gap-2">
              <Badge className={cn("text-[10px]", RISK_STYLES[finding.level])}>
                {RISK_LABELS[finding.level] ?? finding.level}
              </Badge>
              <span className="text-sm font-medium">{finding.category}</span>
              {finding.legal_basis && (
                <span className="text-[11px] font-mono">{finding.legal_basis}</span>
              )}
              {finding.confidence != null && (
                <span className="text-[10px] text-muted-foreground">
                  уверенность {finding.confidence}
                </span>
              )}
              {finding.reviewer_decision && (
                <Badge variant="outline" className="text-[10px]">
                  решение: {finding.reviewer_decision}
                </Badge>
              )}
            </div>

            <p className="text-xs leading-relaxed">{finding.explanation}</p>

            {finding.case_facts.length > 0 && (
              <p className="text-[11px] text-muted-foreground">
                Факты дела: {finding.case_facts.join("; ")}
              </p>
            )}

            {/* Цитаты — включая отклонённые: специалист должен видеть,
                что именно система не приняла. */}
            {finding.citations.map((citation) => (
              <div
                key={citation.id}
                className={cn(
                  "rounded-md border px-2.5 py-2",
                  citation.is_trustworthy
                    ? "border-border"
                    : "border-destructive/40 bg-destructive/5",
                )}
              >
                <div className="flex flex-wrap items-center gap-2">
                  <span className="text-[10px] font-mono text-muted-foreground">
                    {citation.anchor ?? citation.source_ref ?? "источник"}
                  </span>
                  <Badge
                    variant={citation.is_trustworthy ? "secondary" : "destructive"}
                    className="text-[10px]"
                  >
                    {CITATION_STATUS_LABELS[citation.status] ?? citation.status}
                  </Badge>
                  {citation.matched_ratio != null && (
                    <span className="text-[10px] text-muted-foreground">
                      совпало {citation.matched_ratio}
                    </span>
                  )}
                </div>
                <p className="text-[11px] mt-1 italic">«{citation.quote}»</p>
              </div>
            ))}

            {finding.recommended_action && (
              <p className="text-[11px]">
                <span className="font-medium">Рекомендация:</span>{" "}
                {finding.recommended_action}
              </p>
            )}

            {finding.missing_data.length > 0 && (
              <p className="text-[11px] text-muted-foreground">
                Не хватает: {finding.missing_data.join("; ")}
              </p>
            )}

            <div className="flex flex-wrap gap-2 pt-1">
              <Button
                size="sm"
                variant="outline"
                disabled={busyFinding === finding.id}
                onClick={() => void review(finding.id, "approve")}
              >
                <Check className="w-3.5 h-3.5 mr-1.5" />
                Согласен
              </Button>
              <Button
                size="sm"
                variant="ghost"
                disabled={busyFinding === finding.id}
                onClick={() => void review(finding.id, "reject")}
              >
                <X className="w-3.5 h-3.5 mr-1.5" />
                Не согласен
              </Button>
              <Button
                size="sm"
                variant="ghost"
                disabled={busyFinding === finding.id}
                onClick={() => void review(finding.id, "modify")}
              >
                Требует доработки
              </Button>
            </div>
          </CardContent>
        </Card>
      ))}

      {assessment.limitations.length > 0 && (
        <Card>
          <CardHeader className="pb-2">
            <CardTitle className="text-sm font-semibold flex items-center gap-1.5">
              <AlertTriangle className="w-3.5 h-3.5 text-amber-600" />
              Ограничения анализа
            </CardTitle>
          </CardHeader>
          <CardContent className="space-y-1">
            {assessment.limitations.map((item, index) => (
              <p key={index} className="text-[11px] text-muted-foreground">
                • {item}
              </p>
            ))}
          </CardContent>
        </Card>
      )}
    </div>
  );
}
