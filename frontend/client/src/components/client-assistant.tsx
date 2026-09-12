import { useMemo, useState } from "react";
import { useLocation } from "wouter";
import { Bot, Loader2, Send, Sparkles, UserRound } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Switch } from "@/components/ui/switch";
import {
  Sheet,
  SheetContent,
  SheetDescription,
  SheetHeader,
  SheetTitle,
  SheetTrigger,
} from "@/components/ui/sheet";
import { api, ApiError } from "@/lib/api";
import { cn } from "@/lib/utils";

type ChatMessage = { role: "user" | "assistant"; content: string; sources?: string[]; supporting_sources?: Array<{ title: string; url: string; quote: string }> };

const QUICK_QUESTIONS = [
  "Что такое класс МКТУ?",
  "Почему мне предложены эти классы?",
  "Что может помешать регистрации?",
];

export function ClientAssistant() {
  const [location] = useLocation();
  const applicationId = useMemo(() => {
    const match = location.match(/^\/applications\/(\d+)/);
    return match ? Number(match[1]) : null;
  }, [location]);
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [question, setQuestion] = useState("");
  const [loading, setLoading] = useState(false);
  const [useCaseContext, setUseCaseContext] = useState(false);

  const ask = async (value: string) => {
    const clean = value.trim();
    if (!clean || loading) return;
    const userMessage: ChatMessage = { role: "user", content: clean };
    const history = messages.slice(-6).map(({ role, content }) => ({ role, content }));
    setMessages((old) => [...old, userMessage]);
    setQuestion("");
    setLoading(true);
    try {
      const result = await api.post<{ answer: string; sources: string[]; supporting_sources: Array<{ title: string; url: string; quote: string }> }>("/assistant/ask", {
        question: clean,
        application_id: useCaseContext ? applicationId : null,
        history,
      });
      setMessages((old) => [
        ...old,
        { role: "assistant", content: result.answer, sources: result.sources, supporting_sources: result.supporting_sources },
      ]);
    } catch (error) {
      setMessages((old) => [
        ...old,
        {
          role: "assistant",
          content: error instanceof ApiError ? error.message : "Не удалось получить ответ. Попробуйте ещё раз.",
        },
      ]);
    } finally {
      setLoading(false);
    }
  };

  return (
    <Sheet>
      <SheetTrigger asChild>
        <Button
          className="fixed z-40 h-13 max-w-[calc(100vw-2.5rem)] whitespace-nowrap rounded-full bg-[#38322e] px-5 text-white shadow-[0_14px_35px_rgba(17,17,63,0.28)] transition-[transform,box-shadow,background-color] duration-200 hover:-translate-y-0.5 hover:bg-[#584b41] hover:shadow-[0_18px_42px_rgba(17,17,63,0.34)] motion-reduce:transform-none"
          style={{
            right: "max(1.25rem, env(safe-area-inset-right))",
            bottom: "max(6rem, calc(env(safe-area-inset-bottom) + 1.5rem))",
          }}
        >
          <Sparkles className="h-5 w-5 text-[#d7c4a4]" />
          <span className="hidden sm:inline">Спросить помощника</span>
          <span className="sm:hidden">Помощник</span>
        </Button>
      </SheetTrigger>
      <SheetContent side="right" className="client-light-scope registr-v3 flex w-full flex-col border-l-[#38322e]/10 bg-[#fbfaf7] p-0 sm:max-w-[28rem]">
        <SheetHeader className="border-b border-[#38322e]/10 bg-white px-6 py-6 pr-12 text-left">
          <div className="flex items-center gap-3">
            <span className="flex h-11 w-11 items-center justify-center rounded-full bg-[#f0e9dc] text-[#786341]">
              <Bot className="h-5 w-5" />
            </span>
            <div>
              <SheetTitle className="text-[#38322e]">Помощник Регистра</SheetTitle>
              <SheetDescription className="mt-1">Объясняет регистрацию простыми словами</SheetDescription>
            </div>
          </div>
          {applicationId && (
            <label className="mt-4 flex cursor-pointer items-start gap-3 rounded-xl bg-[#fcfbf8] p-3 text-left">
              <Switch
                checked={useCaseContext}
                onCheckedChange={setUseCaseContext}
                className="mt-0.5 shrink-0"
                aria-label="Учитывать текущую заявку"
              />
              <span>
                <span className="block text-sm font-semibold text-[#38322e]">Учитывать мою заявку</span>
                <span className="mt-1 block text-xs leading-relaxed text-[#746e66]">
                  В GigaChat передаются название знака, описание деятельности, классы и результат проверки. Реквизиты и файлы не передаются.
                </span>
              </span>
            </label>
          )}
        </SheetHeader>

        <div className="flex-1 space-y-4 overflow-y-auto px-5 py-5">
          <MessageBubble role="assistant" content={applicationId && useCaseContext ? "Я учитываю текущую заявку и могу объяснить предложенные классы, результат проверки и следующие действия. Что непонятно?" : "Спросите меня о товарных знаках, классах МКТУ, документах, пошлинах или порядке регистрации. Чтобы обсудить конкретную заявку, включите переключатель сверху."} />

          {messages.length === 0 && (
            <div className="space-y-2">
              {QUICK_QUESTIONS.filter((item) => useCaseContext || item !== "Почему мне предложены эти классы?").map((item) => (
                <button key={item} type="button" onClick={() => void ask(item)} className="block w-full rounded-xl border border-[#38322e]/10 bg-white px-4 py-3 text-left text-sm font-medium text-[#38322e] transition-colors hover:border-[#9b8258]/40 hover:bg-[#f4f1eb]">
                  {item}
                </button>
              ))}
            </div>
          )}

          {messages.map((message, index) => (
            <MessageBubble key={index} {...message} />
          ))}
          {loading && <MessageBubble role="assistant" content="" loading />}
        </div>

        <form
          className="border-t border-[#38322e]/10 bg-white p-4"
          onSubmit={(event) => { event.preventDefault(); void ask(question); }}
        >
          <div className="flex gap-2">
            <Input value={question} onChange={(event) => setQuestion(event.target.value)} placeholder="Например: почему выбран класс 35?" className="h-11 rounded-xl" maxLength={2000} />
            <Button type="submit" size="icon" disabled={!question.trim() || loading} className="h-11 w-11 shrink-0 rounded-xl bg-[#9b8258] hover:bg-[#786341]" aria-label="Отправить вопрос">
              {loading ? <Loader2 className="h-4 w-4 animate-spin" /> : <Send className="h-4 w-4" />}
            </Button>
          </div>
          <p className="mt-2 text-center text-[11px] leading-relaxed text-[#746e66]">Отвечает только о регистрации товарных знаков. Не заменяет юридическую консультацию.</p>
        </form>
      </SheetContent>
    </Sheet>
  );
}

function MessageBubble({ role, content, sources, supporting_sources, loading = false }: ChatMessage & { loading?: boolean }) {
  const assistant = role === "assistant";
  return (
    <div className={cn("flex gap-2.5", assistant ? "justify-start" : "justify-end")}>
      {assistant && <span className="mt-1 flex h-7 w-7 shrink-0 items-center justify-center rounded-full bg-[#f0e9dc] text-[#786341]"><Bot className="h-3.5 w-3.5" /></span>}
      <div className={cn("max-w-[84%] rounded-2xl px-4 py-3 text-sm leading-relaxed", assistant ? "rounded-tl-sm border border-[#38322e]/8 bg-white text-[#51483f]" : "rounded-tr-sm bg-[#38322e] text-white")}>
        {loading ? <span className="flex items-center gap-2 text-[#746e66]"><Loader2 className="h-4 w-4 animate-spin" /> Думаю…</span> : <p className="whitespace-pre-wrap">{content}</p>}
        {assistant && supporting_sources?.map((source, index) => <details key={`${source.url}-${index}`} className="mt-2 border-t pt-2 text-xs text-[#746e66]"><summary className="cursor-pointer">Основание ответа: {source.title}</summary><blockquote className="mt-2 border-l-2 pl-2">{source.quote}</blockquote><a href={source.url} target="_blank" rel="noreferrer" className="mt-2 inline-block underline">Открыть источник</a></details>)}
      </div>
      {!assistant && <span className="mt-1 flex h-7 w-7 shrink-0 items-center justify-center rounded-full bg-[#38322e]/10 text-[#38322e]"><UserRound className="h-3.5 w-3.5" /></span>}
    </div>
  );
}
