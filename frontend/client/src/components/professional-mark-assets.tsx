import { useEffect, useRef, useState } from "react";
import { Download, ImageIcon, Loader2, Music, Trash2, Upload } from "lucide-react";
import { api, ApiError, type SourceDocumentDto } from "@/lib/api";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { useToast } from "@/hooks/use-toast";

interface MarkImageDto {
  document_id: number; filename: string; width: number; height: number; format: string;
  dominant_colors: string[]; recognized_text: string; ocr_confidence: number | null;
  visual_search_supported: boolean; visual_search_notice: string;
}

export function ProfessionalMarkAssets({ appId, markType }: { appId: number; markType: string }) {
  const { toast } = useToast();
  const imageInput = useRef<HTMLInputElement>(null);
  const audioInput = useRef<HTMLInputElement>(null);
  const [image, setImage] = useState<MarkImageDto | null>(null);
  const [imageUrl, setImageUrl] = useState<string | null>(null);
  const [audio, setAudio] = useState<SourceDocumentDto | null>(null);
  const [busy, setBusy] = useState(false);
  const imageApplicable = markType === "figurative" || markType === "combined";
  const audioApplicable = markType === "sound";

  const load = async () => {
    const [imageData, docs] = await Promise.all([
      api.get<MarkImageDto>(`/applications/${appId}/mark-image`).catch(() => null),
      api.get<{ items: SourceDocumentDto[] }>(`/applications/${appId}/source-documents`).catch(() => ({ items: [] })),
    ]);
    setImage(imageData);
    setAudio(docs.items.filter((item) => item.document_kind === "mark_audio").at(-1) || null);
    if (imageData) {
      const blob = await api.blob(`/applications/${appId}/mark-image/content`).catch(() => null);
      if (blob) setImageUrl((old) => { if (old) URL.revokeObjectURL(old); return URL.createObjectURL(blob); });
    } else setImageUrl((old) => { if (old) URL.revokeObjectURL(old); return null; });
  };
  useEffect(() => { void load(); return () => { if (imageUrl) URL.revokeObjectURL(imageUrl); }; }, [appId]);

  const uploadImage = async (file?: File) => {
    if (!file) return; setBusy(true);
    try { await api.upload(`/applications/${appId}/mark-image`, file); await load(); toast({ title: "Изображение обозначения обновлено" }); }
    catch (error) { toast({ title: "Изображение не загружено", description: error instanceof ApiError ? error.message : "Используйте PNG или JPEG", variant: "destructive" }); }
    finally { setBusy(false); if (imageInput.current) imageInput.current.value = ""; }
  };
  const uploadAudio = async (file?: File) => {
    if (!file) return; setBusy(true);
    try {
      const document = await api.upload<SourceDocumentDto>(`/applications/${appId}/source-documents`, file);
      if (document.document_kind !== "mark_audio") await api.put(`/source-documents/${document.id}/kind`, { document_kind: "mark_audio" });
      await load(); toast({ title: "Аудиозапись обозначения загружена" });
    } catch (error) { toast({ title: "Аудиозапись не загружена", description: error instanceof ApiError ? error.message : "Используйте MP3 или WAV", variant: "destructive" }); }
    finally { setBusy(false); if (audioInput.current) audioInput.current.value = ""; }
  };
  const removeImage = async () => {
    setBusy(true); try { await api.delete(`/applications/${appId}/mark-image`); await load(); toast({ title: "Изображение отвязано" }); }
    catch (error) { toast({ title: "Не удалось удалить изображение", description: error instanceof ApiError ? error.message : "Попробуйте ещё раз", variant: "destructive" }); }
    finally { setBusy(false); }
  };

  return <Card className="border border-card-border lg:col-span-2">
    <CardHeader className="pb-2"><CardTitle className="text-sm font-semibold">Материалы обозначения</CardTitle></CardHeader>
    <CardContent>
      {!imageApplicable && !audioApplicable && <p className="text-sm text-muted-foreground">Для словесного знака отдельный файл обозначения не требуется. Измените вид знака выше, если знак содержит графику или звук.</p>}
      {imageApplicable && <div className="grid gap-4 md:grid-cols-[220px_1fr]">
        <div className="flex min-h-40 items-center justify-center overflow-hidden rounded-lg border bg-white">{imageUrl ? <img src={imageUrl} alt="Обозначение" className="max-h-52 max-w-full object-contain" /> : <ImageIcon className="h-10 w-10 text-muted-foreground/40" />}</div>
        <div><div className="flex flex-wrap gap-2"><input ref={imageInput} type="file" accept=".png,.jpg,.jpeg" className="hidden" onChange={(event) => void uploadImage(event.target.files?.[0])} /><Button size="sm" onClick={() => imageInput.current?.click()} disabled={busy}>{busy ? <Loader2 className="mr-2 h-4 w-4 animate-spin" /> : <Upload className="mr-2 h-4 w-4" />}{image ? "Заменить изображение" : "Загрузить изображение"}</Button>{image && <Button size="sm" variant="outline" onClick={removeImage} disabled={busy}><Trash2 className="mr-2 h-4 w-4" />Отвязать</Button>}</div>
          {image && <div className="mt-4 space-y-2 text-sm"><p><span className="text-muted-foreground">Файл:</span> {image.filename} · {image.width}×{image.height}</p><p><span className="text-muted-foreground">OCR-текст:</span> {image.recognized_text || "не найден"}</p><div className="flex flex-wrap gap-1">{image.dominant_colors.map((color) => <Badge key={color} variant="outline"><span className="mr-1 h-3 w-3 rounded-full border" style={{ backgroundColor: color }} />{color}</Badge>)}</div><p className="text-xs text-muted-foreground">{image.visual_search_notice}</p></div>}
        </div>
      </div>}
      {audioApplicable && <div className="flex flex-col gap-3 rounded-lg border p-4 sm:flex-row sm:items-center sm:justify-between"><div className="flex items-center gap-3"><Music className="h-6 w-6 text-primary" /><div><p className="text-sm font-semibold">{audio?.original_filename || "Аудиозапись не загружена"}</p><p className="text-xs text-muted-foreground">MP3 или WAV; описание звучания заполняется в карточке обозначения.</p></div></div><div className="flex gap-2"><input ref={audioInput} type="file" accept=".mp3,.wav" className="hidden" onChange={(event) => void uploadAudio(event.target.files?.[0])} />{audio && <Button size="sm" variant="outline" onClick={() => api.download(`/source-documents/${audio.id}/download`, audio.original_filename)}><Download className="mr-2 h-4 w-4" />Скачать</Button>}<Button size="sm" onClick={() => audioInput.current?.click()} disabled={busy}><Upload className="mr-2 h-4 w-4" />{audio ? "Заменить" : "Загрузить"}</Button></div></div>}
    </CardContent>
  </Card>;
}
