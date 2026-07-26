import { useMemo, useState } from "react";
import { Link, useRoute } from "wouter";
import { useCases } from "@/lib/use-cases";
import { AsyncSection } from "@/components/async-states";
import {
  CLIENT_TYPE_LABELS,
  STATUS_LABELS,
  STATUS_COLORS,
  MARK_TYPE_LABELS,
} from "@shared/schema";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Input } from "@/components/ui/input";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { Search, Building2 } from "lucide-react";
import { cn } from "@/lib/utils";

export function ClientsListPage() {
  const [search, setSearch] = useState("");
  const state = useCases();

  const clients = useMemo(() => {
    const all = Object.values(state.data?.clientsById ?? {});
    if (!search) return all;
    const query = search.toLowerCase();
    return all.filter(
      (client) =>
        client.fullNameOrCompanyName.toLowerCase().includes(query) ||
        client.shortName.toLowerCase().includes(query) ||
        (client.inn ?? "").includes(query),
    );
  }, [state.data, search]);

  const countFor = (clientId: number) =>
    (state.data?.applications ?? []).filter((app) => app.clientId === clientId).length;

  return (
    <div className="space-y-4" data-testid="clients-page">
      <h1 className="text-xl font-bold">Клиенты</h1>

      <Card className="border border-card-border">
        <CardContent className="p-4">
          <div className="relative">
            <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-muted-foreground" />
            <Input
              placeholder="Поиск по наименованию или ИНН..."
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              className="pl-9"
              data-testid="input-search-clients"
            />
          </div>
        </CardContent>
      </Card>

      <AsyncSection
        state={state}
        loadingLabel="Загрузка клиентов…"
        emptyTitle="Клиентов нет"
      >
        {() => (
          <Card className="border border-card-border overflow-hidden">
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>Наименование</TableHead>
                  <TableHead className="hidden md:table-cell">Тип</TableHead>
                  <TableHead className="hidden lg:table-cell">ИНН</TableHead>
                  <TableHead className="hidden lg:table-cell">Контакт</TableHead>
                  <TableHead className="w-20">Дел</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {clients.map((client) => (
                  <TableRow key={client.id} data-testid={`client-row-${client.id}`}>
                    <TableCell>
                      <Link href={`/clients/${client.id}`}>
                        <span className="font-medium text-sm hover:text-primary cursor-pointer">
                          {client.shortName}
                        </span>
                      </Link>
                      <p className="text-[11px] text-muted-foreground">
                        {client.fullNameOrCompanyName}
                      </p>
                    </TableCell>
                    <TableCell className="hidden md:table-cell text-sm text-muted-foreground">
                      {CLIENT_TYPE_LABELS[client.type]}
                    </TableCell>
                    <TableCell className="hidden lg:table-cell text-sm font-mono text-muted-foreground">
                      {client.inn || "—"}
                    </TableCell>
                    <TableCell className="hidden lg:table-cell text-sm text-muted-foreground">
                      {client.email || client.phone || "—"}
                    </TableCell>
                    <TableCell className="text-sm">{countFor(client.id)}</TableCell>
                  </TableRow>
                ))}
                {clients.length === 0 && (
                  <TableRow>
                    <TableCell
                      colSpan={5}
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

export function ClientDetailPage() {
  const [, params] = useRoute("/clients/:id");
  const clientId = params?.id ? parseInt(params.id) : 0;
  const state = useCases();

  return (
    <AsyncSection
      state={state}
      loadingLabel="Загрузка клиента…"
      emptyTitle="Клиент не найден"
    >
      {(data) => {
        const client = data.clientsById[clientId];
        if (!client) {
          return (
            <div className="flex items-center justify-center min-h-[40vh]">
              <p className="text-muted-foreground text-sm">Клиент не найден</p>
            </div>
          );
        }
        const applications = data.applications.filter(
          (app) => app.clientId === clientId,
        );

        return (
          <div className="space-y-4" data-testid="client-detail-page">
            <div className="flex items-center gap-3">
              <Building2 className="w-5 h-5 text-primary" />
              <div>
                <h1 className="text-xl font-bold">{client.shortName}</h1>
                <p className="text-sm text-muted-foreground">
                  {client.fullNameOrCompanyName}
                </p>
              </div>
            </div>

            <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
              <Card className="border border-card-border">
                <CardHeader className="pb-2">
                  <CardTitle className="text-sm font-semibold">Реквизиты</CardTitle>
                </CardHeader>
                <CardContent className="space-y-2">
                  <Row label="Тип" value={CLIENT_TYPE_LABELS[client.type]} />
                  <Row label="ИНН" value={client.inn || "—"} mono />
                  <Row label="ОГРН/ОГРНИП" value={client.ogrnOrOgrnip || "—"} mono />
                  <Row label="Адрес" value={client.address || "—"} />
                </CardContent>
              </Card>

              <Card className="border border-card-border">
                <CardHeader className="pb-2">
                  <CardTitle className="text-sm font-semibold">Контакты</CardTitle>
                </CardHeader>
                <CardContent className="space-y-2">
                  <Row label="Контактное лицо" value={client.contactPerson || "—"} />
                  <Row label="Email" value={client.email || "—"} />
                  <Row label="Телефон" value={client.phone || "—"} />
                </CardContent>
              </Card>
            </div>

            <Card className="border border-card-border">
              <CardHeader className="pb-2">
                <CardTitle className="text-sm font-semibold">
                  Дела клиента ({applications.length})
                </CardTitle>
              </CardHeader>
              <CardContent className="space-y-2">
                {applications.length === 0 ? (
                  <p className="text-xs text-muted-foreground">
                    По этому клиенту дел пока нет.
                  </p>
                ) : (
                  applications.map((app) => (
                    <div
                      key={app.id}
                      className="flex items-center justify-between gap-2 border-b border-border pb-2 last:border-0"
                    >
                      <div className="min-w-0">
                        <Link href={`/applications/${app.id}`}>
                          <span className="text-sm font-medium hover:text-primary cursor-pointer">
                            {app.markName}
                          </span>
                        </Link>
                        <p className="text-[11px] text-muted-foreground">
                          #{app.id} · {MARK_TYPE_LABELS[app.markType]}
                        </p>
                      </div>
                      <Badge className={cn("text-[10px]", STATUS_COLORS[app.status])}>
                        {STATUS_LABELS[app.status]}
                      </Badge>
                    </div>
                  ))
                )}
              </CardContent>
            </Card>
          </div>
        );
      }}
    </AsyncSection>
  );
}

function Row({
  label,
  value,
  mono,
}: {
  label: string;
  value: string;
  mono?: boolean;
}) {
  return (
    <div className="flex justify-between gap-3">
      <span className="text-muted-foreground text-xs">{label}</span>
      <span className={cn("text-right text-xs", mono && "font-mono")}>{value}</span>
    </div>
  );
}
