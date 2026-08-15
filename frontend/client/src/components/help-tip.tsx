import { CircleHelp } from "lucide-react";
import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip";
import { cn } from "@/lib/utils";

export function HelpTip({ text, className }: { text: string; className?: string }) {
  return (
    <Tooltip delayDuration={150}>
      <TooltipTrigger asChild>
        <button
          type="button"
          className={cn(
            "inline-flex h-6 w-6 items-center justify-center rounded-full text-[#77778a] transition-colors hover:bg-[#e8f7f6] hover:text-[#087c78] focus:outline-none focus:ring-2 focus:ring-[#0d9f9b]/40",
            className,
          )}
          aria-label="Показать пояснение"
        >
          <CircleHelp className="h-4 w-4" />
        </button>
      </TooltipTrigger>
      <TooltipContent className="max-w-xs rounded-xl px-3.5 py-3 text-sm leading-relaxed" sideOffset={7}>
        {text}
      </TooltipContent>
    </Tooltip>
  );
}
