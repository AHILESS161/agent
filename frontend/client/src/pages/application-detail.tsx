import { useState } from "react";
import { useCase } from "@/lib/use-cases";
import type { Application, Client } from "@shared/schema";
import { useRoute } from "wouter";
import { useAuth } from "@/lib/auth";
import {
  getApplicationById, getClientById, getUserById,
  getLegalReviewsForApp, getLegalFindings, getConflictResults,
  getClassSuggestions, getRecommendation, getDocPackages,
  getStatusHistory, getCompletenessChecks, getAuditLogs,
  getGoodsServicesItems,
} from "@/lib/mock-data";
import {
  STATUS_LABELS, STATUS_COLORS, MARK_TYPE_LABELS, CLIENT_TYPE_LABELS,
  RISK_LABELS, RISK_COLORS,
  type LegalReview, type LegalFinding, type ConflictSearchResult,
  type NiceClassSuggestion, type CompletenessCheck, type StatusHistoryEntry,
  type AuditLog as AuditLogType,
} from "@shared/schema";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { SourceDocumentsTab } from "@/components/source-documents-tab";
import { FieldConfirmationTab } from "@/components/field-confirmation-tab";
import { DemoDataNotice } from "@/components/demo-data-notice";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { Progress } from "@/components/ui/progress";
import { Separator } from "@/components/ui/separator";
import {
  Collapsible, CollapsibleContent, CollapsibleTrigger,
} from "@/components/ui/collapsible";
import {
  Select, SelectContent, SelectItem, SelectTrigger, SelectValue,
} from "@/components/ui/select";
import {
  Info, Shield, Layers, Crosshair, FileCheck, FileText,
  History, CheckCircle2, XCircle, AlertTriangle, ChevronDown,
  Send, Download, Eye, Clock, ArrowRight, Gavel, Upload, ClipboardList, Loader2, AlertCircle,
  Check, X, Minus, ClipboardCheck,
} from "lucide-react";
import { cn } from "@/lib/utils";

// ========== TAB: GENERAL INFO ==========
function GeneralInfoTab({ app, client }: { app: Application; client: Client | null }) {

  return (
    <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
      <Card className="border border-card-border">
        <CardHeader className="pb-2">
          <CardTitle className="text-sm font-semibold flex items-center gap-2">
            <Info className="w-4 h-4 text-primary" /> Информация о заявке
          </CardTitle>
        </CardHeader>
        <CardContent className="space-y-3">
          <InfoRow label="Номер" value={`#${app.id}`} mono />
          <InfoRow label="Статус">
            <Badge className={cn("text-[10px]", STATUS_COLORS[app.status])}>{STATUS_LABELS[app.status]}</Badge>
          </InfoRow>
          <InfoRow
            label="Исполнитель"
            value={app.assigneeId ? `Пользователь #${app.assigneeId}` : "Не назначен"}
          />
          <InfoRow label="Территория" value={app.territory || "—"} />
          <InfoRow label="Приоритет" value={app.priorityClaim || "Нет"} />
          <InfoRow label="Создана" value={new Date(app.createdAt).toLocaleDateString("ru-RU")} />
          <InfoRow label="Обновлена" value={new Date(app.updatedAt).toLocaleDateString("ru-RU")} />
          {app.notes && <InfoRow label="Примечания" value={app.notes} />}
        </CardContent>
      </Card>

      <Card className="border border-card-border">
        <CardHeader className="pb-2">
          <CardTitle className="text-sm font-semibold">Обозначение</CardTitle>
        </CardHeader>
        <CardContent className="space-y-3">
          <InfoRow label="Наименование" value={app.markName} />
          <InfoRow label="Вид" value={MARK_TYPE_LABELS[app.markType]} />
          {app.markText && <InfoRow label="Текст" value={app.markText} />}
          {app.colorsClaimed && <InfoRow label="Цвета" value={app.colorsClaimed} />}
          {app.transliteration && <InfoRow label="Транслитерация" value={app.transliteration} mono />}
          {app.translation && <InfoRow label="Перевод" value={app.translation} />}
          <InfoRow label="Описание" value={app.descriptionOfMark || "—"} />
        </CardContent>
      </Card>

      {client && (
        <Card className="border border-card-border">
          <CardHeader className="pb-2">
            <CardTitle className="text-sm font-semibold">Клиент</CardTitle>
          </CardHeader>
          <CardContent className="space-y-3">
            <InfoRow label="Наименование" value={client.fullNameOrCompanyName} />
            <InfoRow label="Тип" value={CLIENT_TYPE_LABELS[client.type]} />
            <InfoRow label="Контакт" value={client.contactPerson} />
            <InfoRow label="Email" value={client.email} />
            <InfoRow label="Телефон" value={client.phone} />
            <InfoRow label="ИНН" value={client.inn} mono />
          </CardContent>
        </Card>
      )}

      <Card className="border border-card-border">
        <CardHeader className="pb-2">
          <CardTitle className="text-sm font-semibold">Товары и услуги</CardTitle>
        </CardHeader>
        <CardContent className="space-y-3">
          <InfoRow label="Бизнес-описание" value={app.businessDescription || "—"} />
          <Separator />
          <p className="text-sm">{app.goodsServicesRaw || "Перечень пока не заполнен"}</p>
        </CardContent>
      </Card>
    </div>
  );
}

// ========== TAB: COMPLETENESS ==========
function CompletenessTab({ appId }: { appId: number }) {
  // Данные этой вкладки пока демонстрационные, не из БД.
  const checks = getCompletenessChecks(appId);
  const present = checks.filter(c => c.present).length;
  const pct = checks.length ? Math.round((present / checks.length) * 100) : 0;

  return (
    <div className="space-y-4">
      <Card className="border border-card-border">
        <CardContent className="p-4">
          <div className="flex items-center justify-between mb-2">
            <span className="text-sm font-medium">Полнота данных</span>
            <span className="text-sm font-mono font-bold">{pct}%</span>
          </div>
          <Progress value={pct} className="h-2" />
          <p className="text-xs text-muted-foreground mt-2">{present} из {checks.length} полей заполнены</p>
        </CardContent>
      </Card>

      <Card className="border border-card-border">
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead className="w-8"></TableHead>
              <TableHead>Поле</TableHead>
              <TableHead>Критичность</TableHead>
              <TableHead className="hidden md:table-cell">Кто предоставляет</TableHead>
              <TableHead className="hidden md:table-cell">Причина</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {checks.map((check, i) => (
              <TableRow key={i}>
                <TableCell>
                  {check.present ? (
                    <CheckCircle2 className="w-4 h-4 text-green-600" />
                  ) : (
                    <XCircle className="w-4 h-4 text-red-500" />
                  )}
                </TableCell>
                <TableCell className="text-sm font-medium">{check.label}</TableCell>
                <TableCell>
                  <Badge variant={check.severity === "blocking" ? "destructive" : "secondary"} className="text-[10px]">
                    {check.severity === "blocking" ? "Блокирующее" : "Некритичное"}
                  </Badge>
                </TableCell>
                <TableCell className="hidden md:table-cell text-xs text-muted-foreground">
                  {check.provider === "client" ? "Клиент" : "Менеджер"}
                </TableCell>
                <TableCell className="hidden md:table-cell text-xs text-muted-foreground">
                  {check.reason || "—"}
                </TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>
      </Card>

      {checks.some(c => !c.present) && (
        <Button variant="outline" data-testid="button-request-data">
          <Send className="w-4 h-4 mr-2" />
          Запросить данные у клиента
        </Button>
      )}
    </div>
  );
}

// ========== TAB: LEGAL ANALYSIS ==========
function LegalAnalysisTab({ appId }: { appId: number }) {
  // Данные этой вкладки пока демонстрационные, не из БД.
  const reviews = getLegalReviewsForApp(appId);
  const { user } = useAuth();

  if (reviews.length === 0) {
    return (
      <Card className="border border-card-border">
        <CardContent className="p-8 text-center text-muted-foreground">
          <Shield className="w-8 h-8 mx-auto mb-2 opacity-50" />
          <p className="text-sm">Правовой анализ ещё не проведён</p>
        </CardContent>
      </Card>
    );
  }

  return (
    <div className="space-y-4">
      {reviews.map(review => {
        const findings = getLegalFindings(review.id);
        return (
          <div key={review.id} className="space-y-4">
            <Card className="border border-card-border">
              <CardHeader className="pb-2">
                <div className="flex items-center justify-between">
                  <CardTitle className="text-sm font-semibold flex items-center gap-2">
                    <Shield className="w-4 h-4 text-primary" />
                    Правовой анализ #{review.id}
                  </CardTitle>
                  <div className="flex items-center gap-2">
                    <Badge className={cn("text-[10px]", RISK_COLORS[review.riskLevel])}>
                      Риск: {RISK_LABELS[review.riskLevel]}
                    </Badge>
                    <Badge variant="secondary" className="text-[10px] font-mono">
                      Уверенность: {Math.round(review.confidenceScore * 100)}%
                    </Badge>
                  </div>
                </div>
              </CardHeader>
              <CardContent className="space-y-4">
                <div>
                  <p className="text-xs font-medium text-muted-foreground mb-1">Абсолютные основания</p>
                  <p className="text-sm">{review.absoluteGroundsSummary}</p>
                </div>
                <Separator />
                <div>
                  <p className="text-xs font-medium text-muted-foreground mb-1">Относительные основания</p>
                  <p className="text-sm">{review.relativeGroundsSummary}</p>
                </div>
                {review.overrideReason && (
                  <>
                    <Separator />
                    <div>
                      <p className="text-xs font-medium text-muted-foreground mb-1">Решение рецензента</p>
                      <p className="text-sm">{review.overrideReason}</p>
                    </div>
                  </>
                )}
              </CardContent>
            </Card>

            {findings.length > 0 && (
              <div className="space-y-2">
                <p className="text-xs font-semibold text-muted-foreground uppercase tracking-wide">Находки ({findings.length})</p>
                {findings.map(f => (
                  <Collapsible key={f.id}>
                    <Card className="border border-card-border">
                      <CollapsibleTrigger className="w-full">
                        <div className="flex items-center justify-between p-3">
                          <div className="flex items-center gap-2">
                            <Badge className={cn("text-[10px]", RISK_COLORS[f.severity])}>
                              {RISK_LABELS[f.severity]}
                            </Badge>
                            <span className="text-sm font-medium">{f.groundArticle}</span>
                          </div>
                          <ChevronDown className="w-4 h-4 text-muted-foreground" />
                        </div>
                      </CollapsibleTrigger>
                      <CollapsibleContent>
                        <div className="px-3 pb-3 space-y-2">
                          <p className="text-sm">{f.description}</p>
                          <div className="bg-muted/50 rounded-md p-2">
                            <p className="text-xs font-medium text-muted-foreground">Доказательства</p>
                            <p className="text-xs mt-0.5">{f.evidence}</p>
                          </div>
                          <div className="bg-muted/50 rounded-md p-2">
                            <p className="text-xs font-medium text-muted-foreground">Рекомендация</p>
                            <p className="text-xs mt-0.5">{f.recommendation}</p>
                          </div>
                          <p className="text-[10px] text-muted-foreground">Источник: {f.sourceReference}</p>
                        </div>
                      </CollapsibleContent>
                    </Card>
                  </Collapsible>
                ))}
              </div>
            )}

            {user?.role === "lawyer" && !review.reviewerDecision && (
              <div className="flex gap-2">
                <Button size="sm" data-testid="button-approve-review">
                  <Check className="w-3.5 h-3.5 mr-1.5" /> Утвердить
                </Button>
                <Button size="sm" variant="destructive" data-testid="button-reject-review">
                  <X className="w-3.5 h-3.5 mr-1.5" /> Отклонить
                </Button>
                <Button size="sm" variant="outline" data-testid="button-modify-review">
                  <Minus className="w-3.5 h-3.5 mr-1.5" /> Доработать
                </Button>
              </div>
            )}
          </div>
        );
      })}
    </div>
  );
}

// ========== TAB: NICE CLASSES ==========
function ClassesTab({ appId }: { appId: number }) {
  // Данные этой вкладки пока демонстрационные, не из БД.
  const suggestions = getClassSuggestions(appId);
  const { user } = useAuth();

  if (suggestions.length === 0) {
    return (
      <Card className="border border-card-border">
        <CardContent className="p-8 text-center text-muted-foreground">
          <Layers className="w-8 h-8 mx-auto mb-2 opacity-50" />
          <p className="text-sm">Классы МКТУ ещё не определены</p>
        </CardContent>
      </Card>
    );
  }

  const categoryLabels = { primary: "Основной", secondary: "Дополнительный", borderline: "Спорный" };
  const categoryColors = {
    primary: "bg-green-100 text-green-800 dark:bg-green-900/30 dark:text-green-400",
    secondary: "bg-blue-100 text-blue-800 dark:bg-blue-900/30 dark:text-blue-400",
    borderline: "bg-amber-100 text-amber-800 dark:bg-amber-900/30 dark:text-amber-400",
  };

  return (
    <div className="space-y-4">
      <Card className="border border-card-border overflow-hidden">
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead className="w-16">Класс</TableHead>
              <TableHead>Описание</TableHead>
              <TableHead className="hidden md:table-cell">Категория</TableHead>
              <TableHead className="w-24">Уверенность</TableHead>
              <TableHead className="hidden lg:table-cell">Риск упущения</TableHead>
              <TableHead className="w-28">Статус</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {suggestions.map(s => (
              <TableRow key={s.id} data-testid={`class-row-${s.classNumber}`}>
                <TableCell className="font-mono font-bold text-primary">{s.classNumber}</TableCell>
                <TableCell>
                  <p className="text-sm">{s.classDescription}</p>
                  <p className="text-xs text-muted-foreground mt-0.5">{s.rationale}</p>
                </TableCell>
                <TableCell className="hidden md:table-cell">
                  <Badge className={cn("text-[10px]", categoryColors[s.category])}>
                    {categoryLabels[s.category]}
                  </Badge>
                </TableCell>
                <TableCell>
                  <span className="text-sm font-mono">{Math.round(s.confidence * 100)}%</span>
                </TableCell>
                <TableCell className="hidden lg:table-cell text-xs text-muted-foreground">
                  {s.risksIfOmitted}
                </TableCell>
                <TableCell>
                  {s.approved === true ? (
                    <Badge className="bg-green-100 text-green-800 dark:bg-green-900/30 dark:text-green-400 text-[10px]">
                      <Check className="w-3 h-3 mr-1" /> Одобрен
                    </Badge>
                  ) : s.approved === false ? (
                    <Badge variant="destructive" className="text-[10px]">
                      <X className="w-3 h-3 mr-1" /> Отклонён
                    </Badge>
                  ) : user?.role === "lawyer" ? (
                    <div className="flex gap-1">
                      <Button variant="ghost" size="icon" className="h-6 w-6 text-green-600" data-testid={`approve-class-${s.classNumber}`}>
                        <Check className="w-3.5 h-3.5" />
                      </Button>
                      <Button variant="ghost" size="icon" className="h-6 w-6 text-red-500" data-testid={`reject-class-${s.classNumber}`}>
                        <X className="w-3.5 h-3.5" />
                      </Button>
                    </div>
                  ) : (
                    <Badge variant="secondary" className="text-[10px]">На рассмотрении</Badge>
                  )}
                </TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>
      </Card>
    </div>
  );
}

// ========== TAB: CONFLICTS ==========
function ConflictsTab({ appId }: { appId: number }) {
  // Данные этой вкладки пока демонстрационные, не из БД.
  const conflicts = getConflictResults(appId);
  const { user } = useAuth();

  if (conflicts.length === 0) {
    return (
      <Card className="border border-card-border">
        <CardContent className="p-8 text-center text-muted-foreground">
          <Crosshair className="w-8 h-8 mx-auto mb-2 opacity-50" />
          <p className="text-sm">Поиск конфликтов ещё не проведён</p>
          {user?.role === "lawyer" && (
            <Button size="sm" className="mt-3" data-testid="button-run-conflict-search">
              <Crosshair className="w-3.5 h-3.5 mr-1.5" /> Запустить поиск
            </Button>
          )}
        </CardContent>
      </Card>
    );
  }

  const getSimilarityColor = (score: number) => {
    if (score >= 0.9) return "text-red-600 dark:text-red-400";
    if (score >= 0.7) return "text-amber-600 dark:text-amber-400";
    return "text-green-600 dark:text-green-400";
  };

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <p className="text-sm text-muted-foreground">{conflicts.length} потенциальных конфликтов</p>
        <Button size="sm" variant="outline" data-testid="button-rerun-conflict-search">
          <Crosshair className="w-3.5 h-3.5 mr-1.5" /> Запустить поиск
        </Button>
      </div>

      <Card className="border border-card-border overflow-hidden">
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead>Обозначение</TableHead>
              <TableHead>Правообладатель</TableHead>
              <TableHead>Классы</TableHead>
              <TableHead className="w-20">Сходство</TableHead>
              <TableHead className="hidden md:table-cell w-20">Фонетика</TableHead>
              <TableHead className="hidden lg:table-cell">Основание конфликта</TableHead>
              <TableHead className="w-32">Решение</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {conflicts.map(c => (
              <TableRow key={c.id} data-testid={`conflict-row-${c.id}`}>
                <TableCell className="font-medium text-sm">{c.matchedMark}</TableCell>
                <TableCell className="text-sm text-muted-foreground">{c.owner}</TableCell>
                <TableCell className="font-mono text-sm">{c.classes}</TableCell>
                <TableCell>
                  <span className={cn("font-mono text-sm font-semibold", getSimilarityColor(c.similarityScore))}>
                    {Math.round(c.similarityScore * 100)}%
                  </span>
                </TableCell>
                <TableCell className="hidden md:table-cell">
                  <span className={cn("font-mono text-sm", getSimilarityColor(c.phoneticScore))}>
                    {Math.round(c.phoneticScore * 100)}%
                  </span>
                </TableCell>
                <TableCell className="hidden lg:table-cell text-xs text-muted-foreground">
                  {c.conflictReason}
                </TableCell>
                <TableCell>
                  {c.reviewerDecision ? (
                    <Badge className={cn("text-[10px]",
                      c.reviewerDecision === "approve" ? "bg-green-100 text-green-800 dark:bg-green-900/30 dark:text-green-400" : "bg-red-100 text-red-800"
                    )}>
                      {c.reviewerDecision === "approve" ? "Не блокирует" : c.reviewerDecision === "reject" ? "Блокирует" : "Доработка"}
                    </Badge>
                  ) : user?.role === "lawyer" ? (
                    <Select>
                      <SelectTrigger className="h-7 text-xs w-28" data-testid={`conflict-decision-${c.id}`}>
                        <SelectValue placeholder="Решение" />
                      </SelectTrigger>
                      <SelectContent>
                        <SelectItem value="approve">Не блокирует</SelectItem>
                        <SelectItem value="reject">Блокирует</SelectItem>
                        <SelectItem value="modify">Доработка</SelectItem>
                      </SelectContent>
                    </Select>
                  ) : (
                    <Badge variant="secondary" className="text-[10px]">Ожидание</Badge>
                  )}
                </TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>
      </Card>
    </div>
  );
}

// ========== TAB: RECOMMENDATIONS ==========
function RecommendationsTab({ appId }: { appId: number }) {
  // Данные этой вкладки пока демонстрационные, не из БД.
  const rec = getRecommendation(appId);
  const { user } = useAuth();

  if (!rec) {
    return (
      <Card className="border border-card-border">
        <CardContent className="p-8 text-center text-muted-foreground">
          <Gavel className="w-8 h-8 mx-auto mb-2 opacity-50" />
          <p className="text-sm">Рекомендации ещё не сформированы</p>
        </CardContent>
      </Card>
    );
  }

  return (
    <div className="space-y-4">
      <Card className="border border-card-border">
        <CardHeader className="pb-2">
          <div className="flex items-center justify-between">
            <CardTitle className="text-sm font-semibold flex items-center gap-2">
              <Gavel className="w-4 h-4 text-primary" /> Рекомендационная записка
            </CardTitle>
            <Badge variant="secondary" className="text-[10px] font-mono">
              Уверенность: {Math.round(rec.confidence * 100)}%
            </Badge>
          </div>
        </CardHeader>
        <CardContent className="space-y-4">
          <div>
            <p className="text-xs font-medium text-muted-foreground mb-1">Резюме</p>
            <p className="text-sm">{rec.summary}</p>
          </div>
          <Separator />
          <div>
            <p className="text-xs font-medium text-muted-foreground mb-1">Оценка рисков</p>
            <p className="text-sm">{rec.riskAssessment}</p>
          </div>
          <Separator />
          <div>
            <p className="text-xs font-medium text-muted-foreground mb-1">Рекомендованное действие</p>
            <div className="bg-primary/5 border border-primary/20 rounded-md p-3">
              <p className="text-sm font-medium">{rec.recommendedAction}</p>
            </div>
          </div>
        </CardContent>
      </Card>

      {user?.role === "lawyer" && (
        <div className="flex gap-2">
          <Button size="sm" data-testid="button-approve-recommendation">
            <Check className="w-3.5 h-3.5 mr-1.5" /> Утвердить рекомендацию
          </Button>
          <Button size="sm" variant="outline" data-testid="button-reject-recommendation">
            <X className="w-3.5 h-3.5 mr-1.5" /> Отклонить
          </Button>
        </div>
      )}
    </div>
  );
}

// ========== TAB: DOCUMENTS ==========
function DocumentsTab({ appId }: { appId: number }) {
  // Данные этой вкладки пока демонстрационные, не из БД.
  const docs = getDocPackages(appId);
  const { user } = useAuth();

  if (docs.length === 0) {
    return (
      <Card className="border border-card-border">
        <CardContent className="p-8 text-center text-muted-foreground">
          <FileText className="w-8 h-8 mx-auto mb-2 opacity-50" />
          <p className="text-sm">Документы ещё не сформированы</p>
        </CardContent>
      </Card>
    );
  }

  const statusLabels: Record<string, string> = {
    completed: "Готов",
    pending: "В обработке",
    error: "Ошибка",
  };

  return (
    <div className="space-y-4">
      {docs.map(doc => {
        const approver = doc.approvedBy ? getUserById(doc.approvedBy) : null;
        return (
          <Card key={doc.id} className="border border-card-border">
            <CardContent className="p-4">
              <div className="flex items-center justify-between">
                <div>
                  <p className="text-sm font-medium">Пакет документов #{doc.id}</p>
                  <p className="text-xs text-muted-foreground mt-0.5">
                    Создан: {new Date(doc.createdAt).toLocaleDateString("ru-RU")}
                  </p>
                </div>
                <Badge variant={doc.generationStatus === "closed" ? "default" : "secondary"} className="text-[10px]">
                  {statusLabels[doc.generationStatus] || doc.generationStatus}
                </Badge>
              </div>

              {approver && (
                <p className="text-xs text-muted-foreground mt-2">
                  Утверждён: {approver.fullName} ({doc.approvedAt ? new Date(doc.approvedAt).toLocaleDateString("ru-RU") : ""})
                </p>
              )}

              <div className="flex gap-2 mt-3">
                <Button size="sm" variant="outline" data-testid={`preview-doc-${doc.id}`}>
                  <Eye className="w-3.5 h-3.5 mr-1.5" /> Предпросмотр
                </Button>
                <Button size="sm" variant="outline" data-testid={`download-doc-${doc.id}`}>
                  <Download className="w-3.5 h-3.5 mr-1.5" /> Скачать DOCX
                </Button>
                {user?.role === "lawyer" && !doc.approvedBy && doc.generationStatus === "closed" && (
                  <Button size="sm" data-testid={`approve-doc-${doc.id}`}>
                    <Check className="w-3.5 h-3.5 mr-1.5" /> Утвердить
                  </Button>
                )}
              </div>
            </CardContent>
          </Card>
        );
      })}
    </div>
  );
}

// ========== TAB: STATUS & HISTORY ==========
function StatusHistoryTab({ appId }: { appId: number }) {
  // Данные этой вкладки пока демонстрационные, не из БД.
  const history = getStatusHistory(appId);
  const audit = getAuditLogs(appId);

  return (
    <div className="space-y-6">
      <Card className="border border-card-border">
        <CardHeader className="pb-2">
          <CardTitle className="text-sm font-semibold flex items-center gap-2">
            <History className="w-4 h-4 text-primary" /> Хронология статусов
          </CardTitle>
        </CardHeader>
        <CardContent>
          <div className="relative">
            {history.map((entry, i) => (
              <div key={entry.id} className="flex gap-3 pb-4 last:pb-0">
                <div className="flex flex-col items-center">
                  <div className={cn(
                    "w-3 h-3 rounded-full border-2 shrink-0",
                    i === 0 ? "bg-primary border-primary" : "bg-background border-muted-foreground/30"
                  )} />
                  {i < history.length - 1 && <div className="w-0.5 flex-1 bg-border mt-1" />}
                </div>
                <div className="flex-1 min-w-0 pb-2">
                  <div className="flex items-center gap-2">
                    <Badge className={cn("text-[10px]", STATUS_COLORS[entry.toStatus])}>
                      {STATUS_LABELS[entry.toStatus]}
                    </Badge>
                  </div>
                  {entry.comment && <p className="text-xs mt-1">{entry.comment}</p>}
                  <p className="text-[10px] text-muted-foreground mt-0.5">
                    {entry.changedBy} · {new Date(entry.createdAt).toLocaleDateString("ru-RU", { day: "numeric", month: "short", year: "numeric", hour: "2-digit", minute: "2-digit" })}
                  </p>
                </div>
              </div>
            ))}
            {history.length === 0 && (
              <p className="text-sm text-muted-foreground py-4 text-center">Нет записей</p>
            )}
          </div>
        </CardContent>
      </Card>

      <Card className="border border-card-border">
        <CardHeader className="pb-2">
          <CardTitle className="text-sm font-semibold flex items-center gap-2">
            <ClipboardCheck className="w-4 h-4 text-primary" /> Журнал действий
          </CardTitle>
        </CardHeader>
        <CardContent>
          <div className="space-y-2">
            {audit.map(log => (
              <div key={log.id} className="flex items-start gap-3 p-2 rounded-md hover:bg-accent/50">
                <Clock className="w-3.5 h-3.5 text-muted-foreground mt-0.5 shrink-0" />
                <div className="flex-1 min-w-0">
                  <p className="text-sm">{log.action}</p>
                  <p className="text-[10px] text-muted-foreground">
                    {getUserById(log.userId)?.fullName} · {new Date(log.createdAt).toLocaleDateString("ru-RU", { day: "numeric", month: "short", hour: "2-digit", minute: "2-digit" })}
                  </p>
                </div>
              </div>
            ))}
            {audit.length === 0 && (
              <p className="text-sm text-muted-foreground text-center py-4">Нет записей</p>
            )}
          </div>
        </CardContent>
      </Card>
    </div>
  );
}

// ========== INFO ROW HELPER ==========
function InfoRow({ label, value, mono, children }: { label: string; value?: string; mono?: boolean; children?: React.ReactNode }) {
  return (
    <div className="flex flex-col sm:flex-row sm:items-start gap-1 sm:gap-4">
      <span className="text-xs font-medium text-muted-foreground sm:w-32 shrink-0">{label}</span>
      {children || <span className={cn("text-sm", mono && "font-mono")}>{value || "—"}</span>}
    </div>
  );
}

// ========== MAIN PAGE ==========
export default function ApplicationDetailPage() {
  const [, params] = useRoute("/applications/:id");
  const appId = params?.id ? parseInt(params.id) : 0;
  // Меняется после извлечения реквизитов, чтобы вкладка сверки
  // перечитала данные при следующем открытии.
  const [fieldsRefreshKey, setFieldsRefreshKey] = useState(0);

  // Шапка карточки берётся из API: раньше она читалась из моков и
  // расходилась с реальными данными во вкладках.
  const { data, isLoading, error, reload } = useCase(appId);

  if (isLoading) {
    return (
      <div className="flex items-center justify-center gap-2 min-h-[50vh] text-muted-foreground">
        <Loader2 className="w-4 h-4 animate-spin" />
        <span className="text-sm">Загрузка дела…</span>
      </div>
    );
  }

  if (error || !data) {
    return (
      <div className="flex items-start gap-2 rounded-md border border-destructive/40 bg-destructive/10 px-3 py-2">
        <AlertCircle className="w-4 h-4 shrink-0 mt-0.5 text-destructive" />
        <p className="flex-1 text-sm" data-testid="application-error">
          {error ?? "Дело не найдено"}
        </p>
        <Button variant="ghost" size="sm" onClick={reload}>
          Повторить
        </Button>
      </div>
    );
  }

  const app = data.application;
  const client = data.client;

  return (
    <div className="space-y-4" data-testid="application-detail-page">
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-2">
        <div>
          <div className="flex items-center gap-3">
            <h1 className="text-xl font-bold">{app.markName}</h1>
            <Badge className={cn("text-[10px]", STATUS_COLORS[app.status])}>
              {STATUS_LABELS[app.status]}
            </Badge>
          </div>
          <p className="text-sm text-muted-foreground mt-0.5">
            Заявка #{app.id} · {MARK_TYPE_LABELS[app.markType]}
            {client ? ` · ${client.shortName}` : ""}
          </p>
        </div>
      </div>

      <Tabs defaultValue="general" className="w-full">
        <TabsList className="w-full flex overflow-x-auto justify-start bg-transparent border-b border-border rounded-none h-auto p-0 gap-0">
          {[
            { value: "general", label: "Общие сведения", icon: Info },
            { value: "source-documents", label: "Исходные документы", icon: Upload },
            { value: "fields", label: "Сверка полей", icon: ClipboardList },
            { value: "completeness", label: "Полнота данных", icon: ClipboardCheck },
            { value: "legal", label: "Правовой анализ", icon: Shield },
            { value: "classes", label: "Классы МКТУ", icon: Layers },
            { value: "conflicts", label: "Конфликты", icon: Crosshair },
            { value: "recommendations", label: "Рекомендации", icon: Gavel },
            { value: "documents", label: "Документы", icon: FileText },
            { value: "history", label: "История", icon: History },
          ].map(tab => (
            <TabsTrigger
              key={tab.value}
              value={tab.value}
              className="flex items-center gap-1.5 px-3 py-2.5 text-xs font-medium rounded-none border-b-2 border-transparent data-[state=active]:border-primary data-[state=active]:bg-transparent data-[state=active]:shadow-none whitespace-nowrap"
              data-testid={`tab-${tab.value}`}
            >
              <tab.icon className="w-3.5 h-3.5" />
              <span className="hidden sm:inline">{tab.label}</span>
            </TabsTrigger>
          ))}
        </TabsList>

        <div className="mt-4">
          <TabsContent value="general"><GeneralInfoTab app={app} client={client} /></TabsContent>
          <TabsContent value="source-documents">
            <SourceDocumentsTab appId={appId} onExtracted={() => setFieldsRefreshKey(k => k + 1)} />
          </TabsContent>
          <TabsContent value="fields">
            <FieldConfirmationTab key={fieldsRefreshKey} appId={appId} />
          </TabsContent>
          <TabsContent value="completeness"><DemoDataNotice /><CompletenessTab appId={appId} /></TabsContent>
          <TabsContent value="legal"><DemoDataNotice /><LegalAnalysisTab appId={appId} /></TabsContent>
          <TabsContent value="classes"><DemoDataNotice /><ClassesTab appId={appId} /></TabsContent>
          <TabsContent value="conflicts"><DemoDataNotice /><ConflictsTab appId={appId} /></TabsContent>
          <TabsContent value="recommendations"><DemoDataNotice /><RecommendationsTab appId={appId} /></TabsContent>
          <TabsContent value="documents"><DemoDataNotice /><DocumentsTab appId={appId} /></TabsContent>
          <TabsContent value="history"><DemoDataNotice /><StatusHistoryTab appId={appId} /></TabsContent>
        </div>
      </Tabs>
    </div>
  );
}
