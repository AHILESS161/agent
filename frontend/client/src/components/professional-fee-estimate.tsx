import { useState } from "react";
import { ExternalLink, Loader2, ReceiptText } from "lucide-react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { useApi } from "@/lib/use-api";

interface FeeEstimate {
  can_calculate: boolean;
  class_count: number;
  class_basis: "confirmed" | "suggested" | "none";
  payments: Array<{ code: string; title: string; amount: number; when: string }>;
  filing_total: number | null;
  registration_total: number | null;
  total_electronic: number | null;
  paper_certificate_extra: number;
  paper_certificate_requested: boolean;
  total_selected: number | null;
  source_url: string;
  warnings: string[];
}

const rubles = (value: number | null) =>
  value == null ? "—" : `${new Intl.NumberFormat("ru-RU").format(value)} ₽`;

export function ProfessionalFeeEstimate({ appId }: { appId: number }) {
  const fees = useApi<FeeEstimate>(`/applications/${appId}/fees`);
  const [benefitOpen, setBenefitOpen] = useState(false);

  return (
    <Card className="border border-card-border" data-testid="professional-fee-estimate">
      <CardHeader className="pb-3">
        <div className="flex items-start justify-between gap-4">
          <div>
            <CardTitle className="flex items-center gap-2 text-base">
              <ReceiptText className="h-4 w-4 text-primary" />
              Расчёт пошлин Роспатента
            </CardTitle>
            <p className="mt-1 text-sm text-muted-foreground">
              Предварительная сумма по выбранным классам МКТУ с разбивкой по этапам.
            </p>
          </div>
          {fees.data?.can_calculate && (
            <Badge variant="outline">{fees.data.class_count} кл. МКТУ</Badge>
          )}
        </div>
      </CardHeader>
      <CardContent>
        {fees.isLoading && (
          <div className="flex items-center gap-2 py-6 text-sm text-muted-foreground">
            <Loader2 className="h-4 w-4 animate-spin" /> Рассчитываем пошлины…
          </div>
        )}

        {fees.error && (
          <div className="rounded-md border border-destructive/30 bg-destructive/10 p-3 text-sm text-destructive">
            Не удалось рассчитать пошлины: {fees.error}
          </div>
        )}

        {fees.data && !fees.data.can_calculate && (
          <div className="rounded-md border border-amber-300 bg-amber-50 p-4 text-sm text-amber-900">
            Для расчёта подтвердите хотя бы один класс МКТУ во вкладке «Экспертиза».
          </div>
        )}

        {fees.data?.can_calculate && (
          <div className="space-y-5">
            <div className="grid gap-3 md:grid-cols-3">
              <FeeTotal label="При подаче заявки" value={fees.data.filing_total} />
              <FeeTotal label="После решения о регистрации" value={fees.data.registration_total} />
              <FeeTotal label={fees.data.paper_certificate_requested ? "Итого с бумажным свидетельством" : "Итого"} value={fees.data.total_selected ?? fees.data.total_electronic} accent />
            </div>

            <div className="divide-y rounded-lg border">
              {fees.data.payments.map((payment) => (
                <div key={payment.code} className="flex flex-col justify-between gap-2 p-3 sm:flex-row sm:items-center">
                  <div>
                    <p className="text-sm font-medium">{payment.title}</p>
                    <p className="text-xs text-muted-foreground">Подп. {payment.code} приложения № 1 к Положению о пошлинах · {payment.when}</p>
                  </div>
                  <span className="shrink-0 text-sm font-semibold">{rubles(payment.amount)}</span>
                </div>
              ))}
            </div>

            <p className="text-sm text-muted-foreground">
              {fees.data.paper_certificate_requested ? `Заявитель выбрал бумажное свидетельство; доплата ${rubles(fees.data.paper_certificate_extra)} включена в итог.` : `Бумажное свидетельство не выбрано; при необходимости доплата составит ${rubles(fees.data.paper_certificate_extra)}.`}
            </p>

            <div className="rounded-lg border p-4">
              <div className="flex flex-wrap items-center justify-between gap-3"><div><p className="text-sm font-medium">Льгота или освобождение</p><p className="mt-1 text-xs text-muted-foreground">Применяется только после проверки правового основания и подтверждающего документа.</p></div><Button type="button" variant="outline" size="sm" onClick={() => setBenefitOpen((value) => !value)}>Проверить льготу</Button></div>
              {benefitOpen && <div className="mt-3 rounded-md bg-amber-50 p-3 text-xs leading-relaxed text-amber-900">Для обычной заявки на товарный знак статус физлица, самозанятого, ИП или субъекта МСП сам по себе не уменьшает пошлину. Специальные освобождения, включая п. 13¹ Положения о пошлинах, проверяются вручную; расчёт не меняется до подтверждения.</div>}
            </div>

            {fees.data.warnings.length > 0 && (
              <div className="rounded-md bg-muted/60 p-3 text-xs leading-relaxed text-muted-foreground">
                {fees.data.warnings.map((warning) => <p key={warning}>• {warning}</p>)}
              </div>
            )}

            <a
              href={fees.data.source_url}
              target="_blank"
              rel="noreferrer"
              className="inline-flex items-center gap-1 text-xs font-medium text-primary hover:underline"
            >
              Официальная таблица пошлин Роспатента <ExternalLink className="h-3 w-3" />
            </a>
          </div>
        )}
      </CardContent>
    </Card>
  );
}

function FeeTotal({ label, value, accent = false }: { label: string; value: number | null; accent?: boolean }) {
  return (
    <div className={accent ? "rounded-lg bg-primary p-4 text-primary-foreground" : "rounded-lg bg-muted/60 p-4"}>
      <p className={accent ? "text-xs text-primary-foreground/70" : "text-xs text-muted-foreground"}>{label}</p>
      <p className="mt-1 text-xl font-semibold">{rubles(value)}</p>
    </div>
  );
}
