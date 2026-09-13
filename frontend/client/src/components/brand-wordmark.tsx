import { cn } from "@/lib/utils";
import { brandWidth, brandHeight, brandLetterPath, brandTextPath, brandDotPath } from "./brand-wordmark-paths";

/** Approved variant 06: a gold circled Cyrillic Р and a terminal gold dot. */
export function BrandWordmark({ className }: { className?: string }) {
  return (
    <span className={cn("brand-wordmark inline-flex shrink-0 align-middle", className)} role="img" aria-label="Регистр.">
      <svg viewBox={`0 0 ${brandWidth} ${brandHeight}`} aria-hidden="true" className="brand-wordmark__art" style={{ width: `${brandWidth / 94}em`, height: `${brandHeight / 94}em` }}>
        <circle cx="53" cy="50" r="49" fill="none" stroke="#9b8258" strokeWidth="1.6" />
        <path fill="#9b8258" d={brandLetterPath} />
        <path fill="currentColor" d={brandTextPath} />
        <path fill="#9b8258" d={brandDotPath} />
      </svg>
    </span>
  );
}

/** Decorative and compact use of the same first-letter emblem. */
export function BrandSymbol({ className }: { className?: string }) {
  return <svg className={className} viewBox="0 0 106 106" width="1em" height="1em" aria-hidden="true">
    <circle cx="53" cy="50" r="49" fill="none" stroke="currentColor" strokeWidth="1.6" />
    <path fill="currentColor" d={brandLetterPath} />
  </svg>;
}
