import { useState } from "react";
import { AlertCircle, Archive, CheckCircle2, Download, Loader2, RefreshCw } from "lucide-react";
import { api, ApiError } from "@/lib/api";
import { useApi } from "@/lib/use-api";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { useToast } from "@/hooks/use-toast";

export interface ProfessionalPackageStatus {
  ready: boolean;
  blockers: Array<{ code: string; title: string; action: string; section: string }>;
  warnings: string[];
  documents: Array<{ filename: string; title: string; folder: string; purpose: string }>;
  filing_document_count: number;
  reference_document_count: number;
  class_numbers: number[];
  filing_fee: number | null;
  registration_fee: number | null;
  total_fee: number | null;
}

const TARGET_TAB: Record<string, string> = { data: "data", check: "review", application: "application", fees: "fees" };
const rubles = (value: number | null) => value == null ? "—" : `${value.toLocaleString("ru-RU")} ₽`;

export function ProfessionalFilingPackage({ appId, onNavigate }: { appId: number; onNavigate: (tab: string) => void }) {
  const state = useApi<ProfessionalPackageStatus>(`/applications/${appId}/filing-package`);
  const { toast } = useToast();
  const [downloading, setDownloading] = useState(false);
  const download = async () => {
    setDownloading(true);
    try {
      await api.download(`/applications/${appId}/filing-package/download`, `paket-dlya-podachi-${appId}.zip`);
      toast({ title: "ZIP-пакет скачан", description: "Проверьте заявление и применимость каждого приложения перед передачей клиенту или подачей." });
    } catch (error) {
      toast({ title: "Пакет не скачан", description: error instanceof ApiError ? error.message : "Обновите готовность и повторите", variant: "destructive" });
      state.reload();
    } finally { setDownloading(false); }
  };

  return <div className="space-y-5">
    <Card className={state.data?.ready ? "border-emerald-300" : "border-amber-300"}>
      <CardHeader className={state.data?.ready ? "bg-emerald-50" : "bg-amber-50"}>
        <div className="flex flex-col gap-4 sm:flex-row sm:items-start sm:justify-between">
          <div className="flex items-start gap-3">
            <span className="flex h-10 w-10 items-center justify-center rounded-full bg-white">{state.data?.ready ? <CheckCircle2 className="h-5 w-5 text-emerald-700" /> : <Archive className="h-5 w-5 text-amber-700" />}</span>
            <div><CardTitle>{state.data?.ready ? "Пакет готов к проверке специалистом" : "Пакет ещё не готов"}</CardTitle><p className="mt-1 text-sm text-muted-foreground">Единый ZIP содержит файлы для подачи и отдельные инструкции для клиента.</p></div>
          </div>
          <div className="flex gap-2"><Button variant="outline" onClick={state.reload} disabled={state.isLoading}><RefreshCw className={`mr-2 h-4 w-4 ${state.isLoading ? "animate-spin" : ""}`} />Обновить</Button><Button onClick={download} disabled={!state.data?.ready || downloading}>{downloading ? <Loader2 className="mr-2 h-4 w-4 animate-spin" /> : <Download className="mr-2 h-4 w-4" />}Скачать ZIP</Button></div>
        </div>
      </CardHeader>
      <CardContent className="pt-5">
        {state.isLoading && <p className="text-sm text-muted-foreground"><Loader2 className="mr-2 inline h-4 w-4 animate-spin" />Проверяем комплектность…</p>}
        {state.error && <p className="text-sm text-destructive">Не удалось проверить пакет: {state.error}</p>}
        {state.data && <>
          <div className="grid gap-3 sm:grid-cols-4">
            <Metric label="Для подачи" value={`${state.data.filing_document_count}`} />
            <Metric label="Для клиента" value={`${state.data.reference_document_count}`} />
            <Metric label="Классы МКТУ" value={state.data.class_numbers.join(", ") || "—"} />
            <Metric label="Пошлина при подаче" value={rubles(state.data.filing_fee)} />
          </div>
          {!state.data.ready && <div className="mt-5 rounded-lg border border-amber-200 bg-amber-50 p-4"><p className="font-semibold text-amber-950">Блокирующие пункты: {state.data.blockers.length}</p><div className="mt-3 space-y-2">{state.data.blockers.map((blocker, index) => <button key={`${blocker.code}-${index}`} type="button" onClick={() => onNavigate(TARGET_TAB[blocker.section] || "data")} className="flex w-full items-start gap-3 rounded-md bg-white p-3 text-left hover:ring-1 hover:ring-amber-300"><AlertCircle className="mt-0.5 h-4 w-4 shrink-0 text-amber-700" /><span><span className="block text-sm font-semibold">{blocker.title}</span><span className="mt-0.5 block text-xs text-muted-foreground">{blocker.action} · перейти →</span></span></button>)}</div></div>}
        </>}
      </CardContent>
    </Card>

    {state.data && <div className="grid gap-4 lg:grid-cols-2"><DocumentGroup title="Для подачи в Роспатент" hint="Проверьте эти файлы перед отправкой" documents={state.data.documents.filter((item) => item.folder === "01_ДЛЯ_ПОДАЧИ")} /><DocumentGroup title="Для клиента" hint="Инструкции и расчёты, не прикладываются к заявке" documents={state.data.documents.filter((item) => item.folder === "02_ДЛЯ_ВАС")} /></div>}
    {state.data?.warnings?.length ? <Card><CardHeader><CardTitle className="text-base">Ограничения комплекта</CardTitle></CardHeader><CardContent className="space-y-2 text-sm text-muted-foreground">{state.data.warnings.map((warning) => <p key={warning}>• {warning}</p>)}</CardContent></Card> : null}
  </div>;
}

function Metric({ label, value }: { label: string; value: string }) { return <div className="rounded-lg bg-muted/50 p-3"><p className="text-xs text-muted-foreground">{label}</p><p className="mt-1 text-lg font-semibold">{value}</p></div>; }
function DocumentGroup({ title, hint, documents }: { title: string; hint: string; documents: ProfessionalPackageStatus["documents"] }) { return <Card><CardHeader><CardTitle className="text-base">{title}</CardTitle><p className="text-xs text-muted-foreground">{hint}</p></CardHeader><CardContent className="space-y-2">{documents.length ? documents.map((item) => <div key={`${item.folder}-${item.filename}`} className="rounded-md border p-3"><div className="flex items-center justify-between gap-2"><p className="text-sm font-semibold">{item.title}</p><Badge variant="outline" className="shrink-0">{item.filename.split(".").at(-1)?.toUpperCase()}</Badge></div><p className="mt-1 text-xs text-muted-foreground">{item.purpose}</p></div>) : <p className="text-sm text-muted-foreground">Файлов пока нет.</p>}</CardContent></Card>; }
