import { cn } from "@/lib/utils";

/**
 * Единый векторный wordmark «Регистра».
 *
 * Кириллическая «Р» повторяет фирменную разрезную геометрию: тёмная основа и
 * бирюзовый верхний сегмент. Тонкое кольцо собирает её в самостоятельный знак,
 * но это не буквальная латинская маркировка ®.
 */
export function BrandWordmark({
  className,
  accentEnd = false,
}: {
  className?: string;
  accentEnd?: boolean;
}) {
  return (
    <span
      className={cn("brand-wordmark inline-flex items-center", className)}
      data-accent={accentEnd ? "true" : "false"}
      aria-label="Регистр"
    >
      <svg
        viewBox="0 0 72 72"
        aria-hidden="true"
        className="brand-wordmark__symbol"
      >
        <path
          className="brand-wordmark__ring"
          d="M61.5 50A32 32 0 1 1 61.5 22"
          fill="none"
          strokeWidth="2.6"
          strokeLinecap="round"
        />
        <path
          className="brand-wordmark__letter"
          d="M18.5 13h20.2c12 0 20.3 7.9 20.3 19.6 0 11.8-8.3 19.7-20.3 19.7H29.2V61H18.5V38.7h20.2c6 0 9.6-2.2 9.6-6.1 0-4-3.6-6.2-9.6-6.2h-9.5v6.2H18.5V13Z"
        />
        <path
          className="brand-wordmark__accent"
          d="M18.5 32.6V21c0-4.4 3.6-8 8-8h9v13.4h-6.3v6.2H18.5Z"
        />
      </svg>
      <span className="brand-wordmark__text">егистр</span>
    </span>
  );
}
