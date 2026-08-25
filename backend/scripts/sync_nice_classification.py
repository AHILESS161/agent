"""Синхронизация русскоязычного перечня МКТУ с официального сайта ФИПС.

Скрипт не запускается во время обработки заявки: он формирует версионированный
Markdown-снимок, который затем индексируется обычной командой
``python -m scripts.ingest_knowledge``. Это делает результаты анализа
воспроизводимыми и не ставит работу приложения в зависимость от доступности
сайта ФИПС.

Запуск из каталога ``backend``::

    python -m scripts.sync_nice_classification
"""

from __future__ import annotations

import argparse
import html
import re
import tempfile
import time
from dataclasses import dataclass
from datetime import date
from pathlib import Path

import httpx

EDITION = "МКТУ 13-2026"
EFFECTIVE_FROM = "2026-01-01"
INDEX_URL = "https://www.fips.ru/publication-web/classification/mktu?view=index"
CLASS_LIST_URL = "https://www.fips.ru/publication-web/classification/mktu?view=list"
DETAIL_URL = (
    "https://www.fips.ru/publication-web/classification/mktu"
    "?view=detail&symbol={class_number}"
)
DEFAULT_OUTPUT = (
    Path(__file__).resolve().parents[1]
    / "knowledge"
    / "nice_classification_13_2026.md"
)

_TITLE_RE = re.compile(
    r'<div\s+class="boldtext"><b>(.*?)</b>\s*</div>',
    re.IGNORECASE | re.DOTALL,
)
_ITEM_RE = re.compile(
    r'<div\s+class="oneline\s+name">(.*?)</div>\s*'
    r'<div\s+class="oneline">\s*<div>(\d{6})</div>',
    re.IGNORECASE | re.DOTALL,
)
_TAG_RE = re.compile(r"<[^>]+>")
_SPACE_RE = re.compile(r"\s+")


@dataclass(frozen=True)
class NiceClassPage:
    number: int
    title: str
    items: tuple[tuple[str, str], ...]


def _plain_text(fragment: str) -> str:
    fragment = re.sub(r"<br\s*/?>", " / ", fragment, flags=re.IGNORECASE)
    return _SPACE_RE.sub(" ", html.unescape(_TAG_RE.sub(" ", fragment))).strip()


def parse_class_page(class_number: int, document: str) -> NiceClassPage:
    """Извлечь заголовок класса и русские позиции из HTML-карточки ФИПС."""
    title_match = _TITLE_RE.search(document)
    if not title_match:
        raise ValueError(f"ФИПС не вернул заголовок класса {class_number}")

    items: list[tuple[str, str]] = []
    for name_html, code in _ITEM_RE.findall(document):
        name = _plain_text(name_html)
        if name:
            items.append((code, name))
    if not items:
        raise ValueError(f"ФИПС не вернул перечень позиций класса {class_number}")
    expected_prefix = f"{class_number:02d}"
    invalid_codes = [code for code, _ in items if not code.startswith(expected_prefix)]
    if invalid_codes:
        raise ValueError(
            f"В карточке класса {class_number} найдены чужие коды: {invalid_codes[:3]}"
        )
    codes = [code for code, _ in items]
    if len(codes) != len(set(codes)):
        raise ValueError(f"В карточке класса {class_number} найдены дубли кодов")

    return NiceClassPage(
        number=class_number,
        title=_plain_text(title_match.group(1)),
        items=tuple(items),
    )


def fetch_classes(
    timeout: float = 45.0,
    cache_dir: Path | None = None,
    cache_max_age_seconds: float = 24 * 60 * 60,
) -> list[NiceClassPage]:
    cache_dir = cache_dir or Path(tempfile.gettempdir()) / "registr-nice-13-2026"
    cache_dir.mkdir(parents=True, exist_ok=True)
    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 Chrome/140.0 Safari/537.36"
        ),
        "Accept": "text/html,application/xhtml+xml",
    }
    with httpx.Client(timeout=timeout, follow_redirects=True, headers=headers) as client:
        index = client.get(INDEX_URL)
        index.raise_for_status()
        index.encoding = "utf-8"
        if not re.search(r"13\s*редакция\s*2026", index.text, re.IGNORECASE):
            raise RuntimeError("ФИПС не подтверждает, что опубликована МКТУ 13-2026")

        classes = []
        for number in range(1, 46):
            url = DETAIL_URL.format(class_number=number)
            cache_path = cache_dir / f"class-{number:02d}.html"
            cache_is_fresh = (
                cache_path.exists()
                and time.time() - cache_path.stat().st_mtime
                <= cache_max_age_seconds
            )
            if cache_is_fresh:
                classes.append(
                    parse_class_page(number, cache_path.read_text(encoding="utf-8"))
                )
                continue
            response = None
            for attempt in range(5):
                response = client.get(url)
                if response.status_code != 429:
                    break
                time.sleep(2 ** (attempt + 1))
            assert response is not None
            response.raise_for_status()
            response.encoding = "utf-8"
            parsed = parse_class_page(number, response.text)
            cache_path.write_text(response.text, encoding="utf-8")
            classes.append(parsed)
            time.sleep(4.5)
    return classes


def render_markdown(classes: list[NiceClassPage], retrieved_at: str) -> str:
    if {item.number for item in classes} != set(range(1, 46)):
        raise ValueError("Снимок должен содержать все 45 классов МКТУ")

    lines = [
        f"# {EDITION} — официальный русскоязычный перечень товаров и услуг",
        "",
        f"**Редакция:** {EDITION}",
        f"**Действует с:** {EFFECTIVE_FROM}",
        f"**Получено:** {retrieved_at}",
        "**Источник:** Федеральный институт промышленной собственности (ФИПС)",
        f"**Официальная публикация:** {INDEX_URL}",
        f"**Список классов:** {CLASS_LIST_URL}",
        "",
        "Снимок используется для поиска и предложения классов. Решение о перечне",
        "товаров и услуг подтверждает заявитель или специалист перед подачей.",
        "",
        "---",
        "",
    ]

    for nice_class in classes:
        lines.extend(
            [
                f"### Класс {nice_class.number}. Официальный перечень",
                "",
                f"Официальный заголовок класса: {nice_class.title}",
                "",
            ]
        )
        # Пустая строка после каждых пяти позиций позволяет chunker делить
        # большой класс на ограниченные по размеру фрагменты.
        for index, (code, name) in enumerate(nice_class.items, start=1):
            lines.append(f"- {code} — {name}")
            if index % 5 == 0:
                lines.append("")
        lines.extend(["", ""])

    return "\n".join(lines).rstrip() + "\n"


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--retrieved-at", default=date.today().isoformat())
    parser.add_argument(
        "--refresh",
        action="store_true",
        help="не использовать суточный кэш карточек ФИПС",
    )
    args = parser.parse_args()

    classes = fetch_classes(cache_max_age_seconds=0 if args.refresh else 24 * 60 * 60)
    content = render_markdown(classes, args.retrieved_at)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(content, encoding="utf-8")
    total_items = sum(len(item.items) for item in classes)
    print(f"Сохранено: {args.output} ({len(classes)} классов, {total_items} позиций)")


if __name__ == "__main__":
    main()
