import { useMemo, useState } from "react";
import { Link } from "wouter";
import { Card, CardContent } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { Badge } from "@/components/ui/badge";
import { AsyncSection } from "@/components/async-states";
import { useApi, type AuditEntryDto, type Paginated } from "@/lib/use-api";
import { Search } from "lucide-react";

const ENTITY_LABELS: Record<string, string> = {
  TrademarkApplicationDraft: "Дело",
  SourceDocument: "Документ",
  ExtractedField: "Поле",
  RiskAssessment: "Оценка рисков",
  RiskFinding: "Вывод анализа",
  LegalReview: "Правовой анализ",
  RecommendationMemo: "Рекомендация",
  DocumentPackage: "Пакет документов",
  User: "Пользователь",
};

/** Человекочитаемые названия действий. */
const ACTION_LABELS: Record<string, string> = {
  "document.upload": "Загрузка документа",
  "document.extract": "Извлечение реквизитов",
  "field.accept": "Поле принято",
  "field.edit": "Поле изменено",
  "field.reject": "Поле отклонено",
  "field.leave_empty": "Поле оставлено пустым",
  "risk_analysis.run": "Запуск анализа рисков",
  "nice_classes.suggest": "Подбор классов МКТУ",
  application_create: "Создание дела",
  "memo.approved": "Заключение утверждено",
};

export default function AuditPage() {
  const [search, setSearch] = useState("");
  const state = useApi<Paginated<AuditEntryDto>>("/audit?page=1&page_size=200");

  const filtered = useMemo(() => {
    const items = state.data?.items ?? [];
    if (!search) return items;
    const query = search.toLowerCase();
    return items.filter(
      (entry) =>
        entry.action.toLowerCase().includes(query) ||
        (entry.entity_type ?? "").toLowerCase().includes(query) ||
        String(entry.application_id ?? "").includes(query) ||
        String(entry.user_id ?? "").includes(query),
    );
  }, [state.data, search]);

  return (
    <div className="space-y-4" data-testid="audit-page">
      <h1 className="text-xl font-bold">Журнал аудита</h1>

      <Card className="border border-card-border">
        <CardContent className="p-4">
          <div className="relative">
            <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-muted-foreground" />
            <Input
              placeholder="Поиск по действию, объекту, номеру дела..."
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              className="pl-9"
              data-testid="input-search-audit"
            />
          </div>
        </CardContent>
      </Card>

      <AsyncSection
        state={state}
        loadingLabel="Загрузка журнала…"
        emptyTitle="Записей аудита нет"
        emptyHint="Действия пользователей фиксируются автоматически и появятся здесь."
      >
        {() => (
          <Card className="border border-card-border overflow-hidden">
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead className="w-16">№</TableHead>
                  <TableHead>Действие</TableHead>
                  <TableHead className="hidden md:table-cell">Объект</TableHead>
                  <TableHead className="hidden lg:table-cell">Дело</TableHead>
                  <TableHead className="hidden lg:table-cell">Пользователь</TableHead>
                  <TableHead className="hidden xl:table-cell">IP</TableHead>
                  <TableHead>Дата</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {filtered.map((entry) => (
                  <TableRow key={entry.id} data-testid={`audit-row-${entry.id}`}>
                    <TableCell className="font-mono text-xs text-muted-foreground">
                      {entry.id}
                    </TableCell>
                    <TableCell className="text-sm">
                      {ACTION_LABELS[entry.action] ?? entry.action}
                    </TableCell>
                    <TableCell className="hidden md:table-cell">
                      {entry.entity_type && (
                        <Badge variant="secondary" className="text-[10px]">
                          {ENTITY_LABELS[entry.entity_type] ?? entry.entity_type}
                        </Badge>
                      )}
                    </TableCell>
                    <TableCell className="hidden lg:table-cell text-sm">
                      {entry.application_id ? (
                        <Link href={`/applications/${entry.application_id}`}>
                          <span className="hover:text-primary cursor-pointer">
                            #{entry.application_id}
                          </span>
                        </Link>
                      ) : (
                        "—"
                      )}
                    </TableCell>
                    <TableCell className="hidden lg:table-cell text-sm text-muted-foreground">
                      {entry.user_id ? `#${entry.user_id}` : "—"}
                    </TableCell>
                    <TableCell className="hidden xl:table-cell text-xs font-mono text-muted-foreground">
                      {entry.ip_address ?? "—"}
                    </TableCell>
                    <TableCell className="text-xs text-muted-foreground whitespace-nowrap">
                      {new Date(entry.created_at).toLocaleString("ru-RU")}
                    </TableCell>
                  </TableRow>
                ))}
                {filtered.length === 0 && (
                  <TableRow>
                    <TableCell
                      colSpan={7}
                      className="text-center text-sm text-muted-foreground py-8"
                    >
                      Ничего не найдено
                    </TableCell>
                  </TableRow>
                )}
              </TableBody>
            </Table>
          </Card>
        )}
      </AsyncSection>
    </div>
  );
}
