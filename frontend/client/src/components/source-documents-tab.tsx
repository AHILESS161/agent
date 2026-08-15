import { useCallback, useEffect, useRef, useState } from "react";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { useToast } from "@/hooks/use-toast";
import { AiDisclaimer } from "@/components/ai-disclaimer";
import {
  api,
  ApiError,
  DOCUMENT_KIND_LABELS,
  PROCESSING_STATUS_LABELS,
  type SourceDocumentDto,
} from "@/lib/api";
import {
  AlertCircle,
  Download,
  FileText,
  Loader2,
  RefreshCw,
  ScanSearch,
  Upload,
} from "lucide-react";

const ACCEPTED = ".pdf,.docx,.txt,.png,.jpg,.jpeg";
const CONFIRMABLE_KINDS = [
  "egrul_extract",
  "egrip_extract",
  "trademark_application",
  "power_of_attorney",
  "mark_image",
  "other",
] as const;

function formatSize(bytes: number): string {
  if (bytes < 1024) return `${bytes} Б`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(0)} КБ`;
  return `${(bytes / 1024 / 1024).toFixed(1)} МБ`;
}

interface Props {
  appId: number;
  /** Вызывается после успешного извлечения, чтобы обновить вкладку сверки. */
  onExtracted?: () => void;
  /** Упрощённые подписи без внутренней терминологии для личного кабинета. */
  clientMode?: boolean;
}

export function SourceDocumentsTab({ appId, onExtracted, clientMode = false }: Props) {
  const { toast } = useToast();
  const fileInput = useRef<HTMLInputElement>(null);

  const [documents, setDocuments] = useState<SourceDocumentDto[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [isUploading, setIsUploading] = useState(false);
  const [extractingId, setExtractingId] = useState<number | null>(null);
  const [confirmingKindId, setConfirmingKindId] = useState<number | null>(null);

  const load = useCallback(async () => {
    setError(null);
    try {
      const data = await api.get<{ items: SourceDocumentDto[] }>(
        `/applications/${appId}/source-documents`,
      );
      setDocuments(data.items);
    } catch (e) {
      setDocuments([]);
      setError(e instanceof ApiError ? e.message : "Не удалось загрузить список документов");
    }
  }, [appId]);

  useEffect(() => {
    void load();
  }, [load]);

  const handleUpload = async (file: File) => {
    setIsUploading(true);
    setError(null);
    try {
      const created = await api.upload<SourceDocumentDto>(
        `/applications/${appId}/source-documents`,
        file,
      );
      if (created.warning) {
        // Файл сохранён, но текст извлечь не удалось — это не молчаливый сбой.
        toast({
          title: "Файл сохранён, текст не извлечён",
          description: created.warning,
          variant: "destructive",
        });
      } else {
        toast({
          title: "Документ загружен",
          description: `${created.original_filename} — страниц: ${created.page_count ?? "—"}`,
        });
      }
      await load();
    } catch (e) {
      const message = e instanceof ApiError ? e.message : "Не удалось загрузить файл";
      setError(message);
      toast({ title: "Загрузка отклонена", description: message, variant: "destructive" });
    } finally {
      setIsUploading(false);
      if (fileInput.current) fileInput.current.value = "";
    }
  };

  const handleExtract = async (documentId: number) => {
    setExtractingId(documentId);
    try {
      const result = await api.post<{
        fields_extracted: number;
        preserved_confirmed_fields: number;
      }>(`/source-documents/${documentId}/extract`);
      toast({
        title: "Реквизиты извлечены",
        description:
          `Полей: ${result.fields_extracted}. ` +
          `Сохранено подтверждённых: ${result.preserved_confirmed_fields}. ` +
          `Проверьте значения ниже, на шаге сверки данных.`,
      });
      onExtracted?.();
    } catch (e) {
      toast({
        title: "Извлечение не выполнено",
        description: e instanceof ApiError ? e.message : "Неизвестная ошибка",
        variant: "destructive",
      });
    } finally {
      setExtractingId(null);
    }
  };

  const handleDownload = async (doc: SourceDocumentDto) => {
    try {
      await api.download(`/source-documents/${doc.id}/download`, doc.original_filename);
    } catch (e) {
      toast({
        title: "Не удалось скачать файл",
        description: e instanceof ApiError ? e.message : "Неизвестная ошибка",
        variant: "destructive",
      });
    }
  };

  const handleKindConfirmation = async (documentId: number, documentKind: string) => {
    setConfirmingKindId(documentId);
    try {
      await api.put(`/source-documents/${documentId}/kind`, {
        document_kind: documentKind,
      });
      toast({
        title: "Тип документа подтверждён",
        description: "Теперь система понимает, нужно ли включать файл в пакет для подачи.",
      });
      await load();
    } catch (e) {
      toast({
        title: "Тип документа не сохранён",
        description: e instanceof ApiError ? e.message : "Попробуйте ещё раз",
        variant: "destructive",
      });
    } finally {
      setConfirmingKindId(null);
    }
  };

  // --- состояние загрузки ---
  if (documents === null) {
    return (
      <div className="flex items-center gap-2 py-10 justify-center text-muted-foreground">
        <Loader2 className="w-4 h-4 animate-spin" />
        <span className="text-sm">Загрузка документов…</span>
      </div>
    );
  }

  return (
    <div className="space-y-4" data-testid="source-documents-tab">
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-2">
        <div>
          <h3 className="text-base font-semibold">{clientMode ? "Ваши документы" : "Документы проекта"}</h3>
          <p className="mt-1 text-sm text-muted-foreground">
            {clientMode
              ? "Добавьте файл — система распознает текст и предложит данные для заполнения."
              : "Добавьте выписку или другой документ, из которого нужно перенести данные."}
          </p>
        </div>
        <div className="flex items-center gap-2">
          {!clientMode && <Button variant="outline" size="sm" onClick={() => void load()} data-testid="button-reload-documents">
            <RefreshCw className="w-3.5 h-3.5 mr-1.5" />
            Обновить
          </Button>}
          <Button
            size="sm"
            disabled={isUploading}
            onClick={() => fileInput.current?.click()}
            data-testid="button-upload-document"
          >
            {isUploading ? (
              <Loader2 className="w-3.5 h-3.5 mr-1.5 animate-spin" />
            ) : (
              <Upload className="w-3.5 h-3.5 mr-1.5" />
            )}
            {isUploading ? "Загрузка…" : clientMode ? "Добавить файл" : "Загрузить документ"}
          </Button>
          <input
            ref={fileInput}
            type="file"
            accept={ACCEPTED}
            className="hidden"
            data-testid="input-file"
            onChange={(e) => {
              const file = e.target.files?.[0];
              if (file) void handleUpload(file);
            }}
          />
        </div>
      </div>

      {error && (
        <div
          className="flex items-start gap-2 rounded-md border border-destructive/40 bg-destructive/10 px-3 py-2"
          data-testid="documents-error"
        >
          <AlertCircle className="w-4 h-4 shrink-0 mt-0.5 text-destructive" />
          <div className="flex-1">
            <p className="text-xs text-foreground">{error}</p>
          </div>
          <Button variant="ghost" size="sm" onClick={() => void load()}>
            Повторить
          </Button>
        </div>
      )}

      {/* --- пустое состояние --- */}
      {documents.length === 0 ? (
        <Card className="border-dashed">
          <CardContent className="flex flex-col items-center justify-center py-10 text-center">
            <FileText className="w-8 h-8 text-muted-foreground mb-3" />
            <p className="text-sm font-medium">Документов пока нет</p>
            <p className="text-xs text-muted-foreground mt-1 max-w-sm">
              Загрузите выписку ЕГРЮЛ или заполненный бланк заявки, чтобы
              система извлекла реквизиты заявителя.
            </p>
          </CardContent>
        </Card>
      ) : (
        <div className="space-y-2">
          {documents.map((doc) => {
            const failed = doc.processing_status === "failed";
            const canExtract =
              doc.processing_status === "extracted" &&
              ["egrul_extract", "unknown_registry_extract"].includes(doc.document_kind);

            return (
              <Card key={doc.id} data-testid={`document-${doc.id}`}>
                <CardContent className="p-4">
                  <div className="flex flex-col sm:flex-row sm:items-start justify-between gap-3">
                    <div className="min-w-0 flex-1">
                      <div className="flex items-center gap-2 flex-wrap">
                        <FileText className="w-4 h-4 shrink-0 text-muted-foreground" />
                        <span className="truncate text-base font-semibold">
                          {doc.original_filename}
                        </span>
                        <Badge variant="secondary">
                          {DOCUMENT_KIND_LABELS[doc.document_kind] ?? doc.document_kind}
                        </Badge>
                        {doc.extraction_method === "ocr" && (
                          <Badge variant="outline">Распознано со скана</Badge>
                        )}
                        {!clientMode && doc.kind_requires_confirmation && (
                          <Badge variant="outline">
                            тип требует подтверждения
                          </Badge>
                        )}
                      </div>

                      <p className="mt-1.5 text-sm text-muted-foreground">
                        {formatSize(doc.file_size)}
                        {doc.page_count ? ` · страниц: ${doc.page_count}` : ""}
                        {" · "}
                        {clientMode && doc.processing_status === "extracted"
                          ? "Файл обработан"
                          : PROCESSING_STATUS_LABELS[doc.processing_status] ?? doc.processing_status}
                      </p>

                      {failed && doc.error_message && (
                        <p className="mt-1.5 text-sm text-destructive">
                          {doc.error_message}
                        </p>
                      )}

                      {doc.kind_requires_confirmation && (
                        <div className="mt-3 max-w-md rounded-lg border border-amber-200 bg-amber-50 p-3">
                          <p className="mb-2 text-sm font-medium text-amber-950">
                            Что это за файл?
                          </p>
                          <Select
                            disabled={confirmingKindId === doc.id}
                            onValueChange={(value) => void handleKindConfirmation(doc.id, value)}
                          >
                            <SelectTrigger className="bg-white">
                              <SelectValue placeholder={confirmingKindId === doc.id ? "Сохраняем…" : "Выберите тип документа"} />
                            </SelectTrigger>
                            <SelectContent>
                              {CONFIRMABLE_KINDS.map((kind) => (
                                <SelectItem key={kind} value={kind}>
                                  {DOCUMENT_KIND_LABELS[kind]}
                                </SelectItem>
                              ))}
                            </SelectContent>
                          </Select>
                          <p className="mt-2 text-xs leading-relaxed text-amber-900/75">
                            Подтверждение нужно, чтобы изображение знака, доверенность или другое приложение попали в правильную папку итогового архива.
                          </p>
                        </div>
                      )}
                    </div>

                    <div className="flex items-center gap-2 shrink-0">
                      <Button
                        variant="outline"
                        size="sm"
                        onClick={() => void handleDownload(doc)}
                        data-testid={`button-download-${doc.id}`}
                      >
                        <Download className="w-3.5 h-3.5 mr-1.5" />
                        Скачать
                      </Button>
                      {canExtract && (
                        <Button
                          size="sm"
                          disabled={extractingId === doc.id}
                          onClick={() => void handleExtract(doc.id)}
                          data-testid={`button-extract-${doc.id}`}
                        >
                          {extractingId === doc.id ? (
                            <Loader2 className="w-3.5 h-3.5 mr-1.5 animate-spin" />
                          ) : (
                            <ScanSearch className="w-3.5 h-3.5 mr-1.5" />
                          )}
                          {clientMode ? "Перенести данные" : "Извлечь реквизиты"}
                        </Button>
                      )}
                    </div>
                  </div>
                </CardContent>
              </Card>
            );
          })}
        </div>
      )}

      {!clientMode && <AiDisclaimer compact />}
    </div>
  );
}
