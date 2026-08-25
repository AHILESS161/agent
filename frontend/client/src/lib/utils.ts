import { clsx, type ClassValue } from "clsx"
import { twMerge } from "tailwind-merge"

export function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs))
}

/**
 * Возвращает неформальное обращение для главной страницы.
 * Полное имя хранится в официальном порядке «Фамилия Имя Отчество»,
 * поэтому фамилию здесь намеренно не показываем.
 */
export function getGreetingName(
  preferredName?: string | null,
  fullName?: string | null,
) {
  const preferred = preferredName?.trim()
  if (preferred) return preferred

  const parts = fullName?.trim().split(/\s+/).filter(Boolean) ?? []
  if (parts.some((part) => part.includes("@"))) return ""
  if (parts.length >= 3) return parts.slice(1, 3).join(" ")
  if (parts.length === 2) return parts[1]
  return parts[0] ?? ""
}
