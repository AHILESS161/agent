import { useState, useMemo } from "react";
import { Link } from "wouter";
import { mockAuditLogs, getUserById } from "@/lib/mock-data";
import { Card, CardContent } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { Badge } from "@/components/ui/badge";
import { Search, ClipboardList } from "lucide-react";

export default function AuditPage() {
  const [search, setSearch] = useState("");

  const logs = useMemo(() => {
    const sorted = [...mockAuditLogs].sort((a, b) => new Date(b.createdAt).getTime() - new Date(a.createdAt).getTime());
    if (!search) return sorted;
    const q = search.toLowerCase();
    return sorted.filter(l => {
      const user = getUserById(l.userId);
      return l.action.toLowerCase().includes(q) ||
        l.entityType.toLowerCase().includes(q) ||
        user?.fullName.toLowerCase().includes(q) ||
        (l.applicationId && l.applicationId.toString().includes(q));
    });
  }, [search]);

  const entityLabels: Record<string, string> = {
    application: "Заявка",
    legal_review: "Правовой анализ",
    conflict_search: "Поиск конфликтов",
    document_package: "Документы",
    user: "Пользователь",
  };

  return (
    <div className="space-y-4" data-testid="audit-page">
      <h1 className="text-xl font-bold">Журнал аудита</h1>

      <Card className="border border-card-border">
        <CardContent className="p-4">
          <div className="relative">
            <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-muted-foreground" />
            <Input
              placeholder="Поиск по действию, пользователю, номеру заявки..."
              value={search}
              onChange={e => setSearch(e.target.value)}
              className="pl-9"
              data-testid="input-search-audit"
            />
          </div>
        </CardContent>
      </Card>

      <Card className="border border-card-border overflow-hidden">
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead className="w-40">Дата и время</TableHead>
              <TableHead>Действие</TableHead>
              <TableHead className="hidden md:table-cell">Пользователь</TableHead>
              <TableHead className="hidden md:table-cell">Тип сущности</TableHead>
              <TableHead className="hidden lg:table-cell w-24">Заявка</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {logs.map(log => {
              const user = getUserById(log.userId);
              return (
                <TableRow key={log.id} data-testid={`audit-row-${log.id}`}>
                  <TableCell className="text-xs text-muted-foreground font-mono">
                    {new Date(log.createdAt).toLocaleDateString("ru-RU", { day: "2-digit", month: "2-digit", year: "2-digit" })}{" "}
                    {new Date(log.createdAt).toLocaleTimeString("ru-RU", { hour: "2-digit", minute: "2-digit" })}
                  </TableCell>
                  <TableCell className="text-sm">{log.action}</TableCell>
                  <TableCell className="hidden md:table-cell text-sm text-muted-foreground">
                    {user?.fullName || "—"}
                  </TableCell>
                  <TableCell className="hidden md:table-cell">
                    <Badge variant="secondary" className="text-[10px]">
                      {entityLabels[log.entityType] || log.entityType}
                    </Badge>
                  </TableCell>
                  <TableCell className="hidden lg:table-cell">
                    {log.applicationId ? (
                      <Link href={`/applications/${log.applicationId}`}>
                        <span className="text-xs font-mono text-primary hover:underline cursor-pointer">#{log.applicationId}</span>
                      </Link>
                    ) : "—"}
                  </TableCell>
                </TableRow>
              );
            })}
            {logs.length === 0 && (
              <TableRow>
                <TableCell colSpan={5} className="text-center py-8 text-muted-foreground">
                  Нет записей
                </TableCell>
              </TableRow>
            )}
          </TableBody>
        </Table>
      </Card>
    </div>
  );
}
