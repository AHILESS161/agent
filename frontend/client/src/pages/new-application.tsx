import { useState } from "react";
import { useLocation } from "wouter";
import { useCases } from "@/lib/use-cases";
import { api, ApiError } from "@/lib/api";
import { MARK_TYPE_LABELS, type MarkType, type ClientType, CLIENT_TYPE_LABELS } from "@shared/schema";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Separator } from "@/components/ui/separator";
import { useToast } from "@/hooks/use-toast";
import {
  ArrowLeft, ArrowRight, Check, Users, FileText,
  Package, Info, Search,
} from "lucide-react";
import { cn } from "@/lib/utils";

const STEPS = [
  { label: "Клиент", icon: Users },
  { label: "Обозначение", icon: FileText },
  { label: "Товары и услуги", icon: Package },
  { label: "Дополнительно", icon: Info },
  { label: "Проверка", icon: Check },
];

interface FormData {
  clientId: number | null;
  newClient: {
    type: ClientType;
    fullName: string;
    shortName: string;
    contactPerson: string;
    email: string;
    phone: string;
    address: string;
    inn: string;
    ogrn: string;
  };
  useExisting: boolean;
  markType: MarkType;
  markName: string;
  markText: string;
  colorsClaimed: string;
  transliteration: string;
  translation: string;
  descriptionOfMark: string;
  goodsServicesRaw: string;
  businessDescription: string;
  territory: string;
  priorityClaim: string;
  notes: string;
}

const initialForm: FormData = {
  clientId: null,
  newClient: {
    type: "company",
    fullName: "",
    shortName: "",
    contactPerson: "",
    email: "",
    phone: "",
    address: "",
    inn: "",
    ogrn: "",
  },
  useExisting: true,
  markType: "word",
  markName: "",
  markText: "",
  colorsClaimed: "",
  transliteration: "",
  translation: "",
  descriptionOfMark: "",
  goodsServicesRaw: "",
  businessDescription: "",
  territory: "Российская Федерация",
  priorityClaim: "",
  notes: "",
};

export default function NewApplicationPage() {
  const [step, setStep] = useState(0);
  const [form, setForm] = useState<FormData>(initialForm);
  const [clientSearch, setClientSearch] = useState("");
  const [, setLocation] = useLocation();
  const { toast } = useToast();

  // Список клиентов из API: раньше страница читала демонстрационные данные.
  const cases = useCases();
  const clientList = Object.values(cases.data?.clientsById ?? {});

  const update = (partial: Partial<FormData>) => setForm(prev => ({ ...prev, ...partial }));
  const updateNewClient = (partial: Partial<FormData["newClient"]>) =>
    setForm(prev => ({ ...prev, newClient: { ...prev.newClient, ...partial } }));

  const filteredClients = clientList.filter(c =>
    !clientSearch || c.fullNameOrCompanyName.toLowerCase().includes(clientSearch.toLowerCase()) ||
    c.inn.includes(clientSearch)
  );

  const handleSubmit = async () => {
    if (!form.clientId) {
      toast({
        title: "Не выбран клиент",
        description: "Выберите клиента или создайте нового.",
        variant: "destructive",
      });
      return;
    }
    try {
      const created = await api.post<{ id: number }>("/applications", {
        client_id: form.clientId,
        mark_name: form.markName || null,
        mark_text: form.markText || null,
        mark_type: form.markType || null,
        description_of_mark: form.descriptionOfMark || null,
        business_description: form.businessDescription || null,
        goods_services_raw: form.goodsServicesRaw || null,
        transliteration: form.transliteration || null,
        translation: form.translation || null,
        colors_claimed: form.colorsClaimed || null,
        territory: form.territory || null,
        notes: form.notes || null,
      });
      toast({
        title: "Дело создано",
        description: `Дело №${created.id} сохранено как черновик.`,
      });
      setLocation(`/applications/${created.id}`);
      return;
    } catch (e) {
      toast({
        title: "Не удалось создать дело",
        description: e instanceof ApiError ? e.message : "Неизвестная ошибка",
        variant: "destructive",
      });
      return;
    }
    setLocation("/applications");
  };

  const canNext = () => {
    switch (step) {
      case 0: return form.useExisting ? form.clientId !== null : form.newClient.fullName.length > 0;
      case 1: return form.markName.length > 0;
      case 2: return form.goodsServicesRaw.length > 0;
      case 3: return true;
      case 4: return true;
      default: return false;
    }
  };

  return (
    <div className="max-w-3xl mx-auto space-y-6" data-testid="new-application-page">
      <h1 className="text-xl font-bold">Новая заявка</h1>

      {/* Progress */}
      <div className="flex items-center gap-1">
        {STEPS.map((s, i) => (
          <div key={i} className="flex items-center flex-1">
            <button
              onClick={() => i < step && setStep(i)}
              className={cn(
                "flex items-center gap-1.5 px-2.5 py-1.5 rounded-md text-xs font-medium transition-colors w-full justify-center",
                i === step ? "bg-primary text-primary-foreground" :
                i < step ? "bg-primary/10 text-primary cursor-pointer" :
                "bg-muted text-muted-foreground"
              )}
              data-testid={`wizard-step-${i}`}
            >
              <s.icon className="w-3.5 h-3.5" />
              <span className="hidden sm:inline">{s.label}</span>
            </button>
            {i < STEPS.length - 1 && <div className="w-4 h-px bg-border mx-1 shrink-0" />}
          </div>
        ))}
      </div>

      {/* Step 1: Client */}
      {step === 0 && (
        <Card className="border border-card-border">
          <CardHeader className="pb-3">
            <CardTitle className="text-sm font-semibold">Выбор клиента</CardTitle>
          </CardHeader>
          <CardContent className="space-y-4">
            <div className="flex gap-2">
              <Button
                variant={form.useExisting ? "default" : "outline"}
                size="sm"
                onClick={() => update({ useExisting: true })}
                data-testid="btn-existing-client"
              >
                Существующий клиент
              </Button>
              <Button
                variant={!form.useExisting ? "default" : "outline"}
                size="sm"
                onClick={() => update({ useExisting: false, clientId: null })}
                data-testid="btn-new-client"
              >
                Новый клиент
              </Button>
            </div>

            {form.useExisting ? (
              <div className="space-y-3">
                <div className="relative">
                  <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-muted-foreground" />
                  <Input
                    placeholder="Поиск по названию или ИНН..."
                    value={clientSearch}
                    onChange={e => setClientSearch(e.target.value)}
                    className="pl-9"
                    data-testid="input-client-search"
                  />
                </div>
                <div className="space-y-1 max-h-60 overflow-y-auto">
                  {filteredClients.map(c => (
                    <button
                      key={c.id}
                      onClick={() => update({ clientId: c.id })}
                      className={cn(
                        "w-full text-left p-3 rounded-md border transition-colors",
                        form.clientId === c.id ? "border-primary bg-primary/5" : "border-card-border hover:bg-accent/50"
                      )}
                      data-testid={`select-client-${c.id}`}
                    >
                      <p className="text-sm font-medium">{c.fullNameOrCompanyName}</p>
                      <p className="text-xs text-muted-foreground">ИНН: {c.inn} · {CLIENT_TYPE_LABELS[c.type]}</p>
                    </button>
                  ))}
                </div>
              </div>
            ) : (
              <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
                <div className="sm:col-span-2">
                  <Label className="text-xs">Тип</Label>
                  <Select value={form.newClient.type} onValueChange={(v: ClientType) => updateNewClient({ type: v })}>
                    <SelectTrigger data-testid="select-client-type"><SelectValue /></SelectTrigger>
                    <SelectContent>
                      {(Object.keys(CLIENT_TYPE_LABELS) as ClientType[]).map(t => (
                        <SelectItem key={t} value={t}>{CLIENT_TYPE_LABELS[t]}</SelectItem>
                      ))}
                    </SelectContent>
                  </Select>
                </div>
                <div className="sm:col-span-2">
                  <Label className="text-xs">Полное наименование *</Label>
                  <Input value={form.newClient.fullName} onChange={e => updateNewClient({ fullName: e.target.value })} data-testid="input-client-fullname" />
                </div>
                <div>
                  <Label className="text-xs">Краткое наименование</Label>
                  <Input value={form.newClient.shortName} onChange={e => updateNewClient({ shortName: e.target.value })} data-testid="input-client-shortname" />
                </div>
                <div>
                  <Label className="text-xs">Контактное лицо</Label>
                  <Input value={form.newClient.contactPerson} onChange={e => updateNewClient({ contactPerson: e.target.value })} data-testid="input-client-contact" />
                </div>
                <div>
                  <Label className="text-xs">Email</Label>
                  <Input type="email" value={form.newClient.email} onChange={e => updateNewClient({ email: e.target.value })} data-testid="input-client-email" />
                </div>
                <div>
                  <Label className="text-xs">Телефон</Label>
                  <Input value={form.newClient.phone} onChange={e => updateNewClient({ phone: e.target.value })} data-testid="input-client-phone" />
                </div>
                <div className="sm:col-span-2">
                  <Label className="text-xs">Адрес</Label>
                  <Input value={form.newClient.address} onChange={e => updateNewClient({ address: e.target.value })} data-testid="input-client-address" />
                </div>
                <div>
                  <Label className="text-xs">ИНН</Label>
                  <Input value={form.newClient.inn} onChange={e => updateNewClient({ inn: e.target.value })} data-testid="input-client-inn" />
                </div>
                <div>
                  <Label className="text-xs">ОГРН/ОГРНИП</Label>
                  <Input value={form.newClient.ogrn} onChange={e => updateNewClient({ ogrn: e.target.value })} data-testid="input-client-ogrn" />
                </div>
              </div>
            )}
          </CardContent>
        </Card>
      )}

      {/* Step 2: Mark Details */}
      {step === 1 && (
        <Card className="border border-card-border">
          <CardHeader className="pb-3">
            <CardTitle className="text-sm font-semibold">Обозначение</CardTitle>
          </CardHeader>
          <CardContent className="space-y-4">
            <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
              <div className="sm:col-span-2">
                <Label className="text-xs">Вид обозначения *</Label>
                <Select value={form.markType} onValueChange={(v: MarkType) => update({ markType: v })}>
                  <SelectTrigger data-testid="select-mark-type"><SelectValue /></SelectTrigger>
                  <SelectContent>
                    {(Object.keys(MARK_TYPE_LABELS) as MarkType[]).map(t => (
                      <SelectItem key={t} value={t}>{MARK_TYPE_LABELS[t]}</SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </div>
              <div className="sm:col-span-2">
                <Label className="text-xs">Наименование обозначения *</Label>
                <Input value={form.markName} onChange={e => update({ markName: e.target.value })} placeholder="Например: ТЕХНОПАРК" data-testid="input-mark-name" />
              </div>
              <div className="sm:col-span-2">
                <Label className="text-xs">Текст обозначения</Label>
                <Input value={form.markText} onChange={e => update({ markText: e.target.value })} data-testid="input-mark-text" />
              </div>
              <div>
                <Label className="text-xs">Заявленные цвета</Label>
                <Input value={form.colorsClaimed} onChange={e => update({ colorsClaimed: e.target.value })} placeholder="Красный, синий..." data-testid="input-colors" />
              </div>
              <div>
                <Label className="text-xs">Транслитерация</Label>
                <Input value={form.transliteration} onChange={e => update({ transliteration: e.target.value })} className="font-mono" data-testid="input-transliteration" />
              </div>
              <div className="sm:col-span-2">
                <Label className="text-xs">Перевод</Label>
                <Input value={form.translation} onChange={e => update({ translation: e.target.value })} data-testid="input-translation" />
              </div>
              <div className="sm:col-span-2">
                <Label className="text-xs">Описание обозначения</Label>
                <Textarea value={form.descriptionOfMark} onChange={e => update({ descriptionOfMark: e.target.value })} rows={3} data-testid="input-description-mark" />
              </div>
              <div className="sm:col-span-2">
                <Label className="text-xs">Изображение</Label>
                <div className="border-2 border-dashed border-border rounded-md p-6 text-center text-sm text-muted-foreground">
                  Загрузка изображений будет доступна после подключения бэкенда
                </div>
              </div>
            </div>
          </CardContent>
        </Card>
      )}

      {/* Step 3: Goods & Services */}
      {step === 2 && (
        <Card className="border border-card-border">
          <CardHeader className="pb-3">
            <CardTitle className="text-sm font-semibold">Товары и услуги</CardTitle>
          </CardHeader>
          <CardContent className="space-y-4">
            <div>
              <Label className="text-xs">Описание бизнеса / деятельности</Label>
              <Textarea
                value={form.businessDescription}
                onChange={e => update({ businessDescription: e.target.value })}
                rows={3}
                placeholder="Опишите основную деятельность компании..."
                data-testid="input-business-desc"
              />
            </div>
            <div>
              <Label className="text-xs">Перечень товаров и услуг *</Label>
              <Textarea
                value={form.goodsServicesRaw}
                onChange={e => update({ goodsServicesRaw: e.target.value })}
                rows={5}
                placeholder="Перечислите товары и/или услуги, для которых регистрируется знак..."
                data-testid="input-goods-services"
              />
              <p className="text-[10px] text-muted-foreground mt-1">
                Укажите товары и услуги как можно подробнее. Система автоматически предложит классы МКТУ.
              </p>
            </div>
          </CardContent>
        </Card>
      )}

      {/* Step 4: Additional Info */}
      {step === 3 && (
        <Card className="border border-card-border">
          <CardHeader className="pb-3">
            <CardTitle className="text-sm font-semibold">Дополнительная информация</CardTitle>
          </CardHeader>
          <CardContent className="space-y-4">
            <div>
              <Label className="text-xs">Территория</Label>
              <Input value={form.territory} onChange={e => update({ territory: e.target.value })} data-testid="input-territory" />
            </div>
            <div>
              <Label className="text-xs">Конвенционный приоритет</Label>
              <Input
                value={form.priorityClaim}
                onChange={e => update({ priorityClaim: e.target.value })}
                placeholder="Номер и дата приоритетной заявки (если есть)"
                data-testid="input-priority"
              />
            </div>
            <div>
              <Label className="text-xs">Примечания</Label>
              <Textarea
                value={form.notes}
                onChange={e => update({ notes: e.target.value })}
                rows={3}
                placeholder="Любая дополнительная информация..."
                data-testid="input-notes"
              />
            </div>
          </CardContent>
        </Card>
      )}

      {/* Step 5: Review */}
      {step === 4 && (
        <Card className="border border-card-border">
          <CardHeader className="pb-3">
            <CardTitle className="text-sm font-semibold">Проверка данных</CardTitle>
          </CardHeader>
          <CardContent className="space-y-4">
            <div className="space-y-3">
              <ReviewRow label="Клиент" value={
                form.useExisting
                  ? clientList.find((c) => c.id === form.clientId)?.fullNameOrCompanyName || "—"
                  : form.newClient.fullName || "—"
              } />
              <ReviewRow label="Обозначение" value={form.markName} />
              <ReviewRow label="Вид" value={MARK_TYPE_LABELS[form.markType]} />
              {form.markText && <ReviewRow label="Текст" value={form.markText} />}
              {form.colorsClaimed && <ReviewRow label="Цвета" value={form.colorsClaimed} />}
              <Separator />
              <ReviewRow label="Товары/услуги" value={form.goodsServicesRaw} />
              {form.businessDescription && <ReviewRow label="Бизнес" value={form.businessDescription} />}
              <Separator />
              <ReviewRow label="Территория" value={form.territory} />
              {form.priorityClaim && <ReviewRow label="Приоритет" value={form.priorityClaim} />}
              {form.notes && <ReviewRow label="Примечания" value={form.notes} />}
            </div>
          </CardContent>
        </Card>
      )}

      {/* Navigation */}
      <div className="flex items-center justify-between">
        <Button
          variant="outline"
          onClick={() => setStep(Math.max(0, step - 1))}
          disabled={step === 0}
          data-testid="wizard-prev"
        >
          <ArrowLeft className="w-4 h-4 mr-1.5" /> Назад
        </Button>
        {step < STEPS.length - 1 ? (
          <Button
            onClick={() => setStep(Math.min(STEPS.length - 1, step + 1))}
            disabled={!canNext()}
            data-testid="wizard-next"
          >
            Далее <ArrowRight className="w-4 h-4 ml-1.5" />
          </Button>
        ) : (
          <Button onClick={handleSubmit} data-testid="wizard-submit">
            <Check className="w-4 h-4 mr-1.5" /> Создать заявку
          </Button>
        )}
      </div>
    </div>
  );
}

function ReviewRow({ label, value }: { label: string; value: string }) {
  return (
    <div className="flex flex-col sm:flex-row sm:items-start gap-1 sm:gap-4">
      <span className="text-xs font-medium text-muted-foreground sm:w-32 shrink-0">{label}</span>
      <span className="text-sm">{value}</span>
    </div>
  );
}
