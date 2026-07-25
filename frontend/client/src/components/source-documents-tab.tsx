import { useCallback, useEffect, useRef, useState } from "react";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
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

function formatSize(bytes: number): string {
  if (bytes < 1024) return `${bytes} Б`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(0)} КБ`;
  return `${(bytes / 1024 / 1024).toFixed(1)} МБ`;
}

interface Props {
  appId: number;
  /** Вызывается после успешного извлечения, чтобы обновить вкладку сверки. */
  onExtracted?: () => void;
}

export function SourceDocumentsTab({ appId, onExtracted }: Props) {
  const { toast } = useToast();
  const fileInput = useRef<HTMLInputElement>(null);

  const [documents, setDocuments] = useState<SourceDocumentDto[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [isUploading, setIsUploading] = useState(false);
  const [extractingId, setExtractingId] = useState<number | null>(null);

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
          `Проверьте значения на вкладке «Сверка полей».`,
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
          <h3 className="text-sm font-semibold">Исходные документы</h3>
          <p className="text-xs text-muted-foreground mt-0.5">
            PDF, DOCX, TXT, PNG, JPG. Тип файла проверяется по содержимому.
            Распознавание сканов (OCR) не поддерживается.
          </p>
        </div>
        <div className="flex items-center gap-2">
          <Button variant="outline" size="sm" onClick={() => void load()} data-testid="button-reload-documents">
            <RefreshCw className="w-3.5 h-3.5 mr-1.5" />
            Обновить
          </Button>
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
            {isUploading ? "Загрузка…" : "Загрузить документ"}
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
                <CardContent className="p-3">
                  <div className="flex flex-col sm:flex-row sm:items-start justify-between gap-3">
                    <div className="min-w-0 flex-1">
                      <div className="flex items-center gap-2 flex-wrap">
                        <FileText className="w-4 h-4 shrink-0 text-muted-foreground" />
                        <span className="text-sm font-medium truncate">
                          {doc.original_filename}
                        </span>
                        <Badge variant="secondary" className="text-[10px]">
                          {DOCUMENT_KIND_LABELS[doc.document_kind] ?? doc.document_kind}
                        </Badge>
                        {doc.kind_requires_confirmation && (
                          <Badge variant="outline" className="text-[10px]">
                            тип требует подтверждения
                          </Badge>
                        )}
                      </div>

                      <p className="text-[11px] text-muted-foreground mt-1.5">
                        {formatSize(doc.file_size)}
                        {doc.page_count ? ` · страниц: ${doc.page_count}` : ""}
                        {doc.extraction_method ? ` · ${doc.extraction_method}` : ""}
                        {" · "}
                        {PROCESSING_STATUS_LABELS[doc.processing_status] ??
                          doc.processing_status}
                        {doc.kind_confidence != null
                          ? ` · уверенность типа ${doc.kind_confidence}`
                          : ""}
                      </p>

                      <p className="text-[10px] font-mono text-muted-foreground mt-1 truncate">
                        SHA-256: {doc.sha256}
                      </p>

                      {failed && doc.error_message && (
                        <p className="mt-1.5 text-[11px] text-destructive">
                          {doc.error_message}
                        </p>
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
                          Извлечь реквизиты
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

      <AiDisclaimer compact />
    </div>
  );
}
