import { useState, useMemo } from "react";
import { Link, useRoute } from "wouter";
import { mockClients, getApplicationsByClientId } from "@/lib/mock-data";
import { CLIENT_TYPE_LABELS, STATUS_LABELS, STATUS_COLORS, MARK_TYPE_LABELS } from "@shared/schema";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { Separator } from "@/components/ui/separator";
import { Search, Eye, Users, Building2, User, FileText, Phone, Mail, MapPin } from "lucide-react";
import { cn } from "@/lib/utils";

export function ClientsListPage() {
  const [search, setSearch] = useState("");

  const filtered = useMemo(() => {
    return mockClients.filter(c => {
      if (!search) return true;
      const q = search.toLowerCase();
      return c.fullNameOrCompanyName.toLowerCase().includes(q) ||
        c.inn.includes(q) || c.shortName.toLowerCase().includes(q) ||
        c.email.toLowerCase().includes(q);
    });
  }, [search]);

  return (
    <div className="space-y-4" data-testid="clients-list-page">
      <div className="flex items-center justify-between">
        <h1 className="text-xl font-bold">Клиенты</h1>
      </div>

      <Card className="border border-card-border">
        <CardContent className="p-4">
          <div className="relative">
            <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-muted-foreground" />
            <Input
              placeholder="Поиск по названию, ИНН, email..."
              value={search}
              onChange={e => setSearch(e.target.value)}
              className="pl-9"
              data-testid="input-search-clients"
            />
          </div>
        </CardContent>
      </Card>

      <Card className="border border-card-border overflow-hidden">
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead>Наименование</TableHead>
              <TableHead className="hidden md:table-cell">Тип</TableHead>
              <TableHead className="hidden md:table-cell">ИНН</TableHead>
              <TableHead className="hidden lg:table-cell">Контакт</TableHead>
              <TableHead className="w-20">Заявок</TableHead>
              <TableHead className="w-12"></TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {filtered.map(c => {
              const appCount = getApplicationsByClientId(c.id).length;
              return (
                <TableRow key={c.id} data-testid={`client-row-${c.id}`}>
                  <TableCell>
                    <Link href={`/clients/${c.id}`}>
                      <span className="text-sm font-medium hover:text-primary cursor-pointer">
                        {c.fullNameOrCompanyName}
                      </span>
                    </Link>
                    <p className="text-xs text-muted-foreground">{c.email}</p>
                  </TableCell>
                  <TableCell className="hidden md:table-cell">
                    <Badge variant="secondary" className="text-[10px]">{CLIENT_TYPE_LABELS[c.type]}</Badge>
                  </TableCell>
                  <TableCell className="hidden md:table-cell font-mono text-sm text-muted-foreground">{c.inn}</TableCell>
                  <TableCell className="hidden lg:table-cell text-sm text-muted-foreground">{c.contactPerson}</TableCell>
                  <TableCell className="text-center">
                    <Badge variant="secondary" className="text-[10px]">{appCount}</Badge>
                  </TableCell>
                  <TableCell>
                    <Link href={`/clients/${c.id}`}>
                      <Button variant="ghost" size="icon" className="h-7 w-7" data-testid={`view-client-${c.id}`}>
                        <Eye className="w-3.5 h-3.5" />
                      </Button>
                    </Link>
                  </TableCell>
                </TableRow>
              );
            })}
          </TableBody>
        </Table>
      </Card>
    </div>
  );
}

export function ClientDetailPage() {
  const [, params] = useRoute("/clients/:id");
  const clientId = params?.id ? parseInt(params.id) : 0;
  const client = mockClients.find(c => c.id === clientId);
  const apps = getApplicationsByClientId(clientId);

  if (!client) {
    return (
      <div className="flex items-center justify-center min-h-[50vh]">
        <p className="text-muted-foreground">Клиент не найден</p>
      </div>
    );
  }

  const typeIcon = client.type === "company" ? Building2 : User;
  const TypeIcon = typeIcon;

  return (
    <div className="space-y-6" data-testid="client-detail-page">
      <div className="flex items-center gap-3">
        <div className="p-2.5 rounded-lg bg-primary/10">
          <TypeIcon className="w-5 h-5 text-primary" />
        </div>
        <div>
          <h1 className="text-xl font-bold">{client.fullNameOrCompanyName}</h1>
          <Badge variant="secondary" className="text-[10px] mt-0.5">{CLIENT_TYPE_LABELS[client.type]}</Badge>
        </div>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
        <Card className="border border-card-border">
          <CardHeader className="pb-2">
            <CardTitle className="text-sm font-semibold">Информация</CardTitle>
          </CardHeader>
          <CardContent className="space-y-3">
            <InfoRow icon={User} label="Контактное лицо" value={client.contactPerson} />
            <InfoRow icon={Mail} label="Email" value={client.email} />
            <InfoRow icon={Phone} label="Телефон" value={client.phone} />
            <InfoRow icon={MapPin} label="Адрес" value={client.address} />
            <Separator />
            <div className="grid grid-cols-2 gap-3">
              <div>
                <p className="text-xs text-muted-foreground">ИНН</p>
                <p className="text-sm font-mono">{client.inn}</p>
              </div>
              {client.ogrnOrOgrnip && (
                <div>
                  <p className="text-xs text-muted-foreground">ОГРН/ОГРНИП</p>
                  <p className="text-sm font-mono">{client.ogrnOrOgrnip}</p>
                </div>
              )}
            </div>
            <Separator />
            <p className="text-xs text-muted-foreground">
              Зарегистрирован: {new Date(client.createdAt).toLocaleDateString("ru-RU")}
            </p>
          </CardContent>
        </Card>

        <Card className="border border-card-border">
          <CardHeader className="pb-2">
            <div className="flex items-center justify-between">
              <CardTitle className="text-sm font-semibold flex items-center gap-2">
                <FileText className="w-4 h-4 text-primary" /> Заявки ({apps.length})
              </CardTitle>
            </div>
          </CardHeader>
          <CardContent>
            {apps.length === 0 ? (
              <p className="text-sm text-muted-foreground py-4 text-center">Нет заявок</p>
            ) : (
              <div className="space-y-2">
                {apps.map(app => (
                  <Link key={app.id} href={`/applications/${app.id}`}>
                    <div className="flex items-center justify-between p-3 rounded-lg border border-card-border hover:bg-accent/50 cursor-pointer transition-colors">
                      <div className="min-w-0">
                        <div className="flex items-center gap-2">
                          <span className="text-xs font-mono text-muted-foreground">#{app.id}</span>
                          <span className="text-sm font-medium truncate">{app.markName}</span>
                        </div>
                        <p className="text-xs text-muted-foreground mt-0.5">{MARK_TYPE_LABELS[app.markType]}</p>
                      </div>
                      <Badge className={cn("text-[10px] shrink-0 ml-2", STATUS_COLORS[app.status])}>
                        {STATUS_LABELS[app.status]}
                      </Badge>
                    </div>
                  </Link>
                ))}
              </div>
            )}
          </CardContent>
        </Card>
      </div>
    </div>
  );
}

function InfoRow({ icon: Icon, label, value }: { icon: typeof User; label: string; value: string }) {
  return (
    <div className="flex items-center gap-3">
      <Icon className="w-4 h-4 text-muted-foreground shrink-0" />
      <div>
        <p className="text-xs text-muted-foreground">{label}</p>
        <p className="text-sm">{value}</p>
      </div>
    </div>
  );
}
