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
        viewBox="0 0 48 64"
        aria-hidden="true"
        className="mr-[0.02em] h-[0.94em] w-[0.7em] self-center overflow-visible"
        fill="currentColor"
      >
        <path d="M1 2h11v60H1z" />
        <path d="M14.5 2H29c11.4 0 18 6.2 18 17 0 10.8-6.6 17-18 17H14.5V26h14c5 0 7.5-2.3 7.5-7s-2.5-7-7.5-7h-14z" />
      </svg>
      <span>егист</span>
      <span className={accentEnd ? "text-primary" : undefined}>р</span>
    </span>
  );
}
