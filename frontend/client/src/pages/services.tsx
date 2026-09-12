import { useState } from "react";
import { Link, useSearch } from "wouter";
import { useHashLocation } from "wouter/use-hash-location";
import { ArrowLeft, ArrowRight, FileText, Loader2, Scale } from "lucide-react";
import { OfficeActionResponse } from "@/components/office-action-response";
import { TrademarkComparison } from "@/components/trademark-comparison";
import { Button } from "@/components/ui/button";
import { Label } from "@/components/ui/label";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { useAuth } from "@/lib/auth";
import { useApi, type Paginated } from "@/lib/use-api";

interface ServiceApplication { id: number; mark_name: string | null }

export default function ServicesPage() {
  const { user } = useAuth();
  const [location, navigate] = useHashLocation();
  const routeSearch = useSearch();
  // Direct links keep a query in the hash; wouter navigation puts it before the hash.
  // useSearch also subscribes to changes when only the selected tool/case changes.
  const params = new URLSearchParams(location.split("?")[1] || routeSearch);
  const tool = params.get("tool") === "compare" ? "compare" : "reply";
  const requestedId = params.get("application") || "";
  const [page, setPage] = useState(1);
  const [pending, setPending] = useState(false);
  const applications = useApi<Paginated<ServiceApplication>>(`/applications?page=${page}&page_size=200`);
  const onlyApplication = applications.data?.total === 1 ? applications.data.items[0] : undefined;
  const selectedId = /^\d+$/.test(requestedId) && Number(requestedId) > 0 ? Number(requestedId) : onlyApplication?.id;
  const selected = useApi<ServiceApplication>(selectedId ? `/applications/${selectedId}` : null, { treat404AsEmpty: false });
  const client = user?.role === "client";

  const updateRoute = (nextTool: string, applicationId = selectedId) => {
    const next = new URLSearchParams({ tool: nextTool });
    if (applicationId) next.set("application", String(applicationId));
    navigate(`/services?${next}`);
  };

  return (
    <div className="registr-v3 registr-services space-y-9 rounded-3xl bg-[#fcfbf8] p-1 sm:p-3" data-testid="services-page">
      <header className="mx-auto max-w-3xl text-center">
        <p className="text-xs font-semibold uppercase tracking-[.18em] text-[#746e66]">Инструменты для вашего бренда</p>
        <h1 className="registr-serif mt-5 text-[clamp(2.6rem,5vw,4.7rem)] leading-[1.02]">
          Следующий шаг —<br /><em className="font-normal text-[#9b8258]">с ясной позицией.</em>
        </h1>
        <p className="mx-auto mt-5 max-w-xl text-sm leading-7 text-muted-foreground">
          Подготовьте ответ на уведомление Роспатента или сопоставьте два обозначения.
          Начните с того, что нужно сейчас.
        </p>
      </header>

      <Tabs value={tool} onValueChange={(value) => updateRoute(value)}>
        <TabsList className="registr-service-tabs" aria-label="Выберите инструмент">
          <TabsTrigger value="reply"><FileText className="h-4 w-4" />Ответ Роспатенту</TabsTrigger>
          <TabsTrigger value="compare"><Scale className="h-4 w-4" />Сравнение ТЗ</TabsTrigger>
        </TabsList>
        <TabsContent value="reply" forceMount className="mt-8 space-y-6">
          <section className="rounded-2xl border border-border bg-card p-5 sm:p-7">
            <div className="flex flex-col gap-5 sm:flex-row sm:items-center sm:justify-between">
              <div><h2 className="text-lg font-semibold">Для какой заявки готовим ответ?</h2>
                <p className="mt-1 text-sm text-muted-foreground">Реквизиты и документы возьмём из выбранной заявки.</p></div>
              {selectedId && <Link href={`/applications/${selectedId}?step=response`} aria-disabled={pending || undefined} onClick={(event) => { if (pending) event.preventDefault(); }} className={`inline-flex shrink-0 items-center gap-2 text-sm underline underline-offset-4 ${pending ? "cursor-wait opacity-50" : ""}`}>Открыть заявку<ArrowRight className="h-4 w-4" /></Link>}
            </div>
            {applications.isLoading ? <p className="mt-5 flex items-center gap-2 text-sm" role="status"><Loader2 className="h-4 w-4 animate-spin" />Загружаем заявки…</p>
              : applications.error ? <div className="mt-5" role="alert"><p className="text-sm text-destructive">{applications.error}</p><Button variant="outline" className="mt-3" onClick={applications.reload}>Повторить</Button></div>
              : applications.data?.total === 0 ? <div className="mt-5"><p className="text-sm text-muted-foreground">Сначала добавьте товарный знак, к которому относится уведомление. Затем вернитесь сюда — сведения сохранятся в заявке.</p><Button asChild className="mt-4 rounded-full"><Link href={client ? "/start" : "/intake"}>Добавить товарный знак<ArrowRight className="h-4 w-4" /></Link></Button></div>
              : <div className="mt-5 max-w-xl">
                <Label htmlFor="reply-application">Заявка</Label>
                <select id="reply-application" value={selectedId || ""} disabled={pending} onChange={(event) => updateRoute("reply", Number(event.target.value))} className="mt-2 min-h-12 w-full rounded-xl border border-input bg-background px-4 py-2 text-sm focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-ring disabled:opacity-60">
                  <option value="" disabled>Выберите товарный знак</option>
                  {selectedId && !applications.data?.items.some((item) => item.id === selectedId) && <option value={selectedId}>{selected.data?.mark_name || "Заявка"} · №{selectedId}</option>}
                  {applications.data?.items.map((item) => <option key={item.id} value={item.id}>{item.mark_name || "Без названия"} · №{item.id}</option>)}
                </select>
                {pending && <p className="mt-2 text-xs text-muted-foreground" role="status">Смена заявки доступна после сохранения изменений и завершения обработки.</p>}
                {(applications.data?.total_pages || 0) > 1 && <div className="mt-3 flex items-center gap-3 text-xs"><Button size="icon" variant="outline" aria-label="Предыдущие заявки" disabled={page === 1} onClick={() => setPage((value) => value - 1)}><ArrowLeft className="h-4 w-4" /></Button><span>Страница {page} из {applications.data?.total_pages}</span><Button size="icon" variant="outline" aria-label="Следующие заявки" disabled={page >= (applications.data?.total_pages || 1)} onClick={() => setPage((value) => value + 1)}><ArrowRight className="h-4 w-4" /></Button></div>}
              </div>}
          </section>
          {selectedId && (selected.isLoading ? <p role="status" className="flex items-center justify-center gap-2 py-12"><Loader2 className="h-4 w-4 animate-spin" />Открываем заявку…</p>
            : selected.error ? <div className="rounded-2xl border border-destructive/30 p-6" role="alert"><p>{selected.error}</p><Button className="mt-3" variant="outline" onClick={selected.reload}>Повторить</Button></div>
            : selected.data?.id === selectedId && <div className="rounded-2xl border border-border bg-card p-5 sm:p-8"><OfficeActionResponse key={selectedId} appId={selectedId} audience={client ? "client" : "professional"} compact onPendingChange={setPending} /></div>)}
        </TabsContent>
        <TabsContent value="compare" forceMount className="mt-8"><TrademarkComparison /></TabsContent>
      </Tabs>
    </div>
  );
}
