/**
 * Настройки профиля.
 *
 * Меняются только личные вещи: как зовут, как обращаться и пароль.
 * Роль и адрес почты — вопрос доступа, их назначает администратор,
 * поэтому здесь они показаны, но не редактируются.
 */

import { useState } from "react";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Badge } from "@/components/ui/badge";
import { useToast } from "@/hooks/use-toast";
import { useAuth } from "@/lib/auth";
import { api, ApiError } from "@/lib/api";
import { Loader2, UserRound } from "lucide-react";

const ROLE_LABELS: Record<string, string> = {
  admin: "Администратор",
  lawyer: "Специалист (юрист)",
  manager: "Менеджер",
  client: "Клиент",
};

export default function ProfilePage() {
  const { toast } = useToast();
  const { user, refreshProfile } = useAuth();

  const [fullName, setFullName] = useState(user?.fullName ?? "");
  const [preferredName, setPreferredName] = useState(user?.preferredName ?? "");
  const savedApplicant = user?.applicantProfile;
  const [applicantType, setApplicantType] = useState(savedApplicant?.type ?? "individual");
  const [applicantName, setApplicantName] = useState(savedApplicant?.fullNameOrCompanyName ?? "");
  const [applicantInn, setApplicantInn] = useState(savedApplicant?.inn ?? "");
  const [applicantRegistryNumber, setApplicantRegistryNumber] = useState(savedApplicant?.ogrnOrOgrnip ?? "");
  const [applicantKpp, setApplicantKpp] = useState(savedApplicant?.kpp ?? "");
  const [applicantAddress, setApplicantAddress] = useState(savedApplicant?.address ?? "");
  const [applicantEmail, setApplicantEmail] = useState(savedApplicant?.email ?? user?.email ?? "");
  const [applicantPhone, setApplicantPhone] = useState(savedApplicant?.phone ?? "");
  const [isSaving, setIsSaving] = useState(false);

  const [currentPassword, setCurrentPassword] = useState("");
  const [newPassword, setNewPassword] = useState("");
  const [repeatPassword, setRepeatPassword] = useState("");
  const [isChanging, setIsChanging] = useState(false);

  const describe = (e: unknown) =>
    e instanceof ApiError ? e.message : "Неизвестная ошибка";

  const saveProfile = async () => {
    setIsSaving(true);
    try {
      await api.patch("/auth/me", {
        full_name: fullName.trim() || null,
        preferred_name: preferredName.trim() || null,
        applicant_profile_json: user?.role === "client" ? {
          type: applicantType,
          full_name_or_company_name: applicantName.trim() || null,
          inn: applicantInn.trim() || null,
          ogrn_or_ogrnip: applicantRegistryNumber.trim() || null,
          kpp: applicantKpp.trim() || null,
          address: applicantAddress.trim() || null,
          country: "RU",
          email: applicantEmail.trim() || null,
          phone: applicantPhone.trim() || null,
        } : undefined,
      });
      await refreshProfile();
      toast({ title: "Профиль сохранён" });
    } catch (e) {
      toast({
        title: "Не удалось сохранить профиль",
        description: describe(e),
        variant: "destructive",
      });
    } finally {
      setIsSaving(false);
    }
  };

  const changePassword = async () => {
    if (newPassword !== repeatPassword) {
      toast({
        title: "Пароли не совпадают",
        description: "Повторите новый пароль без ошибок.",
        variant: "destructive",
      });
      return;
    }
    if (newPassword.length < 8) {
      toast({
        title: "Пароль слишком короткий",
        description: "Не менее 8 символов.",
        variant: "destructive",
      });
      return;
    }

    setIsChanging(true);
    try {
      await api.post("/auth/change-password", {
        current_password: currentPassword,
        new_password: newPassword,
      });
      setCurrentPassword("");
      setNewPassword("");
      setRepeatPassword("");
      toast({ title: "Пароль изменён" });
    } catch (e) {
      toast({
        title: "Не удалось изменить пароль",
        description: describe(e),
        variant: "destructive",
      });
    } finally {
      setIsChanging(false);
    }
  };

  if (!user) return null;

  return (
    <div className="space-y-4 max-w-2xl" data-testid="profile-page">
      <div className="flex items-center gap-2">
        <UserRound className="w-5 h-5 text-primary" />
        <div>
          <h1 className="text-xl font-bold">Профиль</h1>
          <p className="text-sm text-muted-foreground">
            Как система обращается к вам и данные для входа
          </p>
        </div>
      </div>

      <Card>
        <CardHeader className="pb-2">
          <CardTitle className="text-sm font-semibold">Личные данные</CardTitle>
        </CardHeader>
        <CardContent className="space-y-3">
          <div className="space-y-1">
            <Label className="text-xs font-medium">Полное имя</Label>
            <Input
              value={fullName}
              onChange={(e) => setFullName(e.target.value)}
              placeholder="Иванова Елена Викторовна"
              data-testid="input-full-name"
            />
            <p className="text-[10px] text-muted-foreground">
              Фамилия, имя и отчество — используются в документах и журнале.
            </p>
          </div>

          <div className="space-y-1">
            <Label className="text-xs font-medium">Как к вам обращаться</Label>
            <Input
              value={preferredName}
              onChange={(e) => setPreferredName(e.target.value)}
              placeholder="Елена"
              data-testid="input-preferred-name"
            />
            <p className="text-[10px] text-muted-foreground">
              Это имя видно в приветствии. Если не заполнить, система возьмёт
              имя из ФИО.
            </p>
          </div>

          <div className="flex flex-wrap items-center gap-3 pt-1">
            <div className="space-y-0.5">
              <p className="text-[10px] text-muted-foreground">Почта</p>
              <p className="text-sm font-mono">{user.email}</p>
            </div>
            <div className="space-y-0.5">
              <p className="text-[10px] text-muted-foreground">Роль</p>
              <Badge variant="secondary" className="text-[10px]">
                {ROLE_LABELS[user.role] ?? user.role}
              </Badge>
            </div>
            <p className="text-[10px] text-muted-foreground basis-full">
              Почту и роль меняет администратор — это вопрос доступа,
              а не личных настроек.
            </p>
          </div>

          <Button
            size="sm"
            disabled={isSaving}
            onClick={() => void saveProfile()}
            data-testid="save-profile"
          >
            {isSaving && <Loader2 className="w-3.5 h-3.5 mr-1.5 animate-spin" />}
            Сохранить
          </Button>
        </CardContent>
      </Card>

      {user.role === "client" && (
        <Card>
          <CardHeader className="pb-2">
            <CardTitle className="text-sm font-semibold">Данные заявителя для новых заявок</CardTitle>
          </CardHeader>
          <CardContent className="space-y-4">
            <p className="text-xs leading-relaxed text-muted-foreground">
              Заполните один раз — при создании следующей заявки эти реквизиты появятся в форме автоматически. Перед каждой подачей их можно изменить.
            </p>
            <div className="space-y-1">
              <Label className="text-xs font-medium">Кто подаёт заявку</Label>
              <select className="flex h-10 w-full rounded-md border border-input bg-background px-3 py-2 text-sm" value={applicantType} onChange={(event) => setApplicantType(event.target.value as typeof applicantType)}>
                <option value="individual">Физическое лицо / самозанятый</option>
                <option value="sole_proprietor">Индивидуальный предприниматель</option>
                <option value="company">Юридическое лицо</option>
              </select>
            </div>
            <div className="space-y-1">
              <Label className="text-xs font-medium">{applicantType === "company" ? "Полное наименование организации" : "Фамилия, имя и отчество"}</Label>
              <Input value={applicantName} onChange={(event) => setApplicantName(event.target.value)} />
            </div>
            <div className="grid gap-3 sm:grid-cols-2">
              <div className="space-y-1"><Label className="text-xs font-medium">ИНН</Label><Input value={applicantInn} onChange={(event) => setApplicantInn(event.target.value)} /></div>
              {applicantType !== "individual" && <div className="space-y-1"><Label className="text-xs font-medium">{applicantType === "company" ? "ОГРН" : "ОГРНИП"}</Label><Input value={applicantRegistryNumber} onChange={(event) => setApplicantRegistryNumber(event.target.value)} /></div>}
              {applicantType === "company" && <div className="space-y-1"><Label className="text-xs font-medium">КПП</Label><Input value={applicantKpp} onChange={(event) => setApplicantKpp(event.target.value)} /></div>}
            </div>
            <div className="space-y-1"><Label className="text-xs font-medium">Адрес заявителя</Label><Input value={applicantAddress} onChange={(event) => setApplicantAddress(event.target.value)} /></div>
            <div className="grid gap-3 sm:grid-cols-2">
              <div className="space-y-1"><Label className="text-xs font-medium">E-mail для переписки</Label><Input type="email" value={applicantEmail} onChange={(event) => setApplicantEmail(event.target.value)} /></div>
              <div className="space-y-1"><Label className="text-xs font-medium">Телефон</Label><Input value={applicantPhone} onChange={(event) => setApplicantPhone(event.target.value)} /></div>
            </div>
            <Button size="sm" disabled={isSaving} onClick={() => void saveProfile()}>
              {isSaving && <Loader2 className="mr-1.5 h-3.5 w-3.5 animate-spin" />} Сохранить данные заявителя
            </Button>
          </CardContent>
        </Card>
      )}

      <Card>
        <CardHeader className="pb-2">
          <CardTitle className="text-sm font-semibold">Смена пароля</CardTitle>
        </CardHeader>
        <CardContent className="space-y-3">
          <div className="space-y-1">
            <Label className="text-xs font-medium">Текущий пароль</Label>
            <Input
              type="password"
              value={currentPassword}
              onChange={(e) => setCurrentPassword(e.target.value)}
              data-testid="input-current-password"
            />
          </div>
          <div className="grid gap-3 sm:grid-cols-2">
            <div className="space-y-1">
              <Label className="text-xs font-medium">Новый пароль</Label>
              <Input
                type="password"
                value={newPassword}
                onChange={(e) => setNewPassword(e.target.value)}
                data-testid="input-new-password"
              />
            </div>
            <div className="space-y-1">
              <Label className="text-xs font-medium">Повторите новый</Label>
              <Input
                type="password"
                value={repeatPassword}
                onChange={(e) => setRepeatPassword(e.target.value)}
                data-testid="input-repeat-password"
              />
            </div>
          </div>
          <Button
            size="sm"
            variant="outline"
            disabled={isChanging || !currentPassword || !newPassword}
            onClick={() => void changePassword()}
            data-testid="change-password"
          >
            {isChanging && <Loader2 className="w-3.5 h-3.5 mr-1.5 animate-spin" />}
            Изменить пароль
          </Button>
        </CardContent>
      </Card>
    </div>
  );
}
