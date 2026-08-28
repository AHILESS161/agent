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

type ChatMessage = { role: "user" | "assistant"; content: string; sources?: string[] };

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
      const result = await api.post<{ answer: string; sources: string[] }>("/assistant/ask", {
        question: clean,
        application_id: useCaseContext ? applicationId : null,
        history,
      });
      setMessages((old) => [
        ...old,
        { role: "assistant", content: result.answer, sources: result.sources },
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
          className="fixed z-40 h-13 max-w-[calc(100vw-2.5rem)] whitespace-nowrap rounded-full bg-[#11113f] px-5 text-white shadow-[0_14px_35px_rgba(17,17,63,0.28)] transition-[transform,box-shadow,background-color] duration-200 hover:-translate-y-0.5 hover:bg-[#22225c] hover:shadow-[0_18px_42px_rgba(17,17,63,0.34)] motion-reduce:transform-none"
          style={{
            right: "max(1.25rem, env(safe-area-inset-right))",
            bottom: "max(6rem, calc(env(safe-area-inset-bottom) + 1.5rem))",
          }}
        >
          <Sparkles className="h-5 w-5 text-[#43c7c2]" />
          <span className="hidden sm:inline">Спросить помощника</span>
          <span className="sm:hidden">Помощник</span>
        </Button>
      </SheetTrigger>
      <SheetContent side="right" className="flex w-full flex-col border-l-[#11113f]/10 bg-[#fbfaf7] p-0 sm:max-w-[28rem]">
        <SheetHeader className="border-b border-[#11113f]/10 bg-white px-6 py-6 pr-12 text-left">
          <div className="flex items-center gap-3">
            <span className="flex h-11 w-11 items-center justify-center rounded-full bg-[#e8f7f6] text-[#087c78]">
              <Bot className="h-5 w-5" />
            </span>
            <div>
              <SheetTitle className="text-[#11113f]">Помощник Регистра</SheetTitle>
              <SheetDescription className="mt-1">Объясняет регистрацию простыми словами</SheetDescription>
            </div>
          </div>
          {applicationId && (
            <label className="mt-4 flex cursor-pointer items-start gap-3 rounded-xl bg-[#f6f5f1] p-3 text-left">
              <Switch
                checked={useCaseContext}
                onCheckedChange={setUseCaseContext}
                className="mt-0.5 shrink-0"
                aria-label="Учитывать текущую заявку"
              />
              <span>
                <span className="block text-sm font-semibold text-[#11113f]">Учитывать мою заявку</span>
                <span className="mt-1 block text-xs leading-relaxed text-[#77778a]">
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
                <button key={item} type="button" onClick={() => void ask(item)} className="block w-full rounded-xl border border-[#11113f]/10 bg-white px-4 py-3 text-left text-sm font-medium text-[#11113f] transition-colors hover:border-[#0d9f9b]/40 hover:bg-[#f0f8f7]">
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
          className="border-t border-[#11113f]/10 bg-white p-4"
          onSubmit={(event) => { event.preventDefault(); void ask(question); }}
        >
          <div className="flex gap-2">
            <Input value={question} onChange={(event) => setQuestion(event.target.value)} placeholder="Например: почему выбран класс 35?" className="h-11 rounded-xl" maxLength={2000} />
            <Button type="submit" size="icon" disabled={!question.trim() || loading} className="h-11 w-11 shrink-0 rounded-xl bg-[#0d9f9b] hover:bg-[#078984]" aria-label="Отправить вопрос">
              {loading ? <Loader2 className="h-4 w-4 animate-spin" /> : <Send className="h-4 w-4" />}
            </Button>
          </div>
          <p className="mt-2 text-center text-[11px] leading-relaxed text-[#77778a]">Отвечает только о регистрации товарных знаков. Не заменяет юридическую консультацию.</p>
        </form>
      </SheetContent>
    </Sheet>
  );
}

function MessageBubble({ role, content, sources, loading = false }: ChatMessage & { loading?: boolean }) {
  const assistant = role === "assistant";
  return (
    <div className={cn("flex gap-2.5", assistant ? "justify-start" : "justify-end")}>
      {assistant && <span className="mt-1 flex h-7 w-7 shrink-0 items-center justify-center rounded-full bg-[#e8f7f6] text-[#087c78]"><Bot className="h-3.5 w-3.5" /></span>}
      <div className={cn("max-w-[84%] rounded-2xl px-4 py-3 text-sm leading-relaxed", assistant ? "rounded-tl-sm border border-[#11113f]/8 bg-white text-[#33334e]" : "rounded-tr-sm bg-[#11113f] text-white")}>
        {loading ? <span className="flex items-center gap-2 text-[#77778a]"><Loader2 className="h-4 w-4 animate-spin" /> Думаю…</span> : <p className="whitespace-pre-wrap">{content}</p>}
        {assistant && sources && sources.length > 0 && <p className="mt-2 border-t border-[#11113f]/8 pt-2 text-[11px] text-[#77778a]">Материалы: {sources.join(", ")}</p>}
      </div>
      {!assistant && <span className="mt-1 flex h-7 w-7 shrink-0 items-center justify-center rounded-full bg-[#11113f]/10 text-[#11113f]"><UserRound className="h-3.5 w-3.5" /></span>}
    </div>
  );
}
