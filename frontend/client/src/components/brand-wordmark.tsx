import { cn } from "@/lib/utils";

/**
 * Wordmark with a deliberately split first letter. The detached bowl gives
 * the Cyrillic «Р» the same stencil-like character as the visual reference
 * and keeps the mark independent from whatever UI font is loaded.
 */
export function BrandWordmark({
  className,
  accentEnd = false,
}: {
  className?: string;
  accentEnd?: boolean;
}) {
  return (
    <span className={cn("brand-wordmark inline-flex items-baseline", className)} aria-label="Регистр">
      <svg
        viewBox="0 0 54 64"
        aria-hidden="true"
        className="mr-[0.01em] h-[0.94em] w-[0.76em] self-center overflow-visible"
        fill="currentColor"
      >
        <path d="M1 2h11v60H1z" />
        <path d="M18 2h14c12.2 0 20 6.4 20 17s-7.8 17-20 17H18V26h13.5c5.7 0 8.5-2.3 8.5-7s-2.8-7-8.5-7H18z" />
      </svg>
      <span>егист</span>
      <span className={accentEnd ? "text-primary" : undefined}>р</span>
    </span>
  );
}
