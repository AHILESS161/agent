"""
ApplicationPdfParserAgent — извлекает данные из заполненного бланка заявки
Роспатента (PDF/DOCX).

Двухуровневое извлечение:
1. Эвристика по кодам INID (WIPO ST.9) и текстовым меткам.
2. LLM-fallback через prompt registry для недостающих полей
   (prompt_id: ``intake.application_pdf_parser_fill_gaps``).

INID-коды формы:
  (210) дата поступления; (220) дата подачи; (731) заявитель;
  (740) представитель; (750) адрес для переписки; (540) обозначение;
  (541) тип; (546)/(591) цвет; (550) вид знака; (551) коллективный;
  (554) объёмный; (555) голографический; (556) звуковой;
  (557) обонятельный; (558) цвет-знак; (571) описание;
  (511) классы МКТУ и товары/услуги; (320) № первой заявки;
  (330) код страны приоритета; (310) дата приоритета;
  (641) первоначальная заявка; (151) международная регистрация.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from typing import Any

from app.agents.base import BaseAgent, StructuredAgentOutput

logger = logging.getLogger(__name__)
_INID_RE = re.compile(r"\((\d{3})\)\s*")
_INN_RE = re.compile(r"(?<!\d)(\d{10}|\d{12})(?!\d)")
_OGRN_RE = re.compile(r"(?<!\d)(\d{13}|\d{15})(?!\d)")
_KPP_RE = re.compile(r"(?<!\d)(\d{9})(?!\d)")
_EMAIL_RE = re.compile(r"[\w.+-]+@[\w.-]+\.[\w.-]+")
_MARK_NAME_QUOTED_RE = re.compile(
    "[\u00ab\u00bb\u201c\u201d]([^\u00ab\u00bb\u201c\u201d]+)"
    "[\u00ab\u00bb\u201c\u201d]"
)

_CLIENT_HEADER_PATTERNS = re.compile(
    r"(?:ЗАЯВИТЕЛЬ\s*\(указывается|"
    r"полное наименование юридического лица|"
    r"полный адрес места нахождения юридического лица|"
    r"фамилия, имя, отчество\s*\(последнее|"
    r"индивидуального предпринимателя и полный адрес|"
    r"название страны|IDЕНТИФИКАТОРЫ ЗАЯВИТЕЛЯ)",
    re.IGNORECASE,
)

_PRIORITY_HEADER_PATTERNS = re.compile(
    r"(?:Прошу\s+установить\s+приоритет|"
    r"подачи\s+первой\s+\(первых\)\s+заявки\s+\(заявок\)|"
    r"в\s+государстве\s*-\s*участнике\s+Парижской\s+конвенции|"
    r"приоритета\s+первоначальной\s+заявки|"
    r"международной\s+регистрации|"
    r"приоритета\s+международной\s+регистрации|"
    r"Прошу\s+установить\s+дату\s+подачи\s+настоящей\s+заявки|"
    r"внесения\s+записи\s+о\s+территориальном\s+расширении|"
    r"пункта\s+\d+\s+статьи\s+\d+\s+Кодекса|"
    r"Собрание\s+законодательства\s+Российской\s+Федерации)",
    re.IGNORECASE,
)

_MARK_TYPE_OPTION_KEYWORDS = re.compile(
    r"\b(словесный|изобразительный|световой|изменяющийся|позиционный|"
    r"осязательный|вкусовой|обонятельный|объемный|объёмный|голографический|"
    r"звуковой|комбинированный|коллективный|"
    r"знак,?\s*состоящий\s+исключительно|"
    r"из\s+одного\s+или\s+нескольких\s+цветов)\b",
    re.IGNORECASE,
)

_NON_DATA_NUMBERS = {
    "1494", "1495", "152", "152-ФЗ", "941", "3451", "2701", "6170", "6639",
    "5496", "356", "127", "2006", "2008", "2020", "2021", "2022", "2023",
    "2024", "2025", "1994", "1995", "1996",
}

_ORG_FORM_RE = re.compile(
    r"\b(ООО|ОАО|ЗАО|ПАО|АО|ИП|ГУП|МУП|ФГБУ|ФГБНУ|ФКУ|ФБУ|"
    r"Общество\s+с\s+ограниченной\s+ответственностью|"
    r"Публичное\s+акционерное\s+общество|"
    r"Акционерное\s+общество|"
    r"Индивидуальный\s+предприниматель|"
    r"Федеральное\s+государственное\s+бюджетное\s+учреждение|"
    r"Государственное\s+унитарное\s+предприятие|"
    r"Муниципальное\s+унитарное\s+предприятие|"
    r"Федеральное\s+государственное\s+казённое\s+учреждение)\b",
    re.IGNORECASE,
)

_FILING_DATE_KEYWORDS = re.compile(
    r"(?:Дата\s+поступления|Дата\s+подачи|"
    r"по\s+испрашивани[юе]\s+даты\s+подачи)",
    re.IGNORECASE,
)

_VALID_COUNTRY_CODES = {
    "RU", "US", "DE", "CN", "JP", "FR", "GB", "IT", "CH", "KR",
    "CA", "AU", "BR", "IN", "TR", "PL", "CZ", "SK", "HU", "RO",
    "BG", "GR", "ES", "PT", "NL", "BE", "AT", "SE", "NO", "FI",
    "DK", "IE", "IL", "AE", "SA", "EG", "ZA", "MX", "AR", "CL",
    "BY", "UA", "KZ", "UZ", "AM", "AZ", "GE", "MD", "TM", "TJ",
    "KG", "LV", "LT", "EE", "SI", "RS", "HR", "BA", "AL", "MK",
    "LU", "MT", "CY", "IS", "LI", "MC", "SM", "VA",
}

_MARK_TYPE_MAP = {
    "словесный": "word",
    "изобразительный": "figurative",
    "комбинированный": "combined",
    "объемный": "3d",
    "объёмный": "3d",
    "звуковой": "sound",
    "световой": "light",
    "изменяющийся": "changing",
    "позиционный": "positional",
    "осязательный": "tactile",
    "вкусовой": "taste",
    "обонятельный": "olfactory",
    "голографический": "holographic",
    "состоящий исключительно из одного или нескольких цветов": "color",
}

_MARK_TYPE_ORDER = [
    "3d", "sound", "light", "changing", "positional",
    "tactile", "taste", "olfactory", "holographic",
    "word", "figurative", "combined", "color",
]


def _priority_block_has_data(block: str) -> bool:
    if not block:
        return False
    cleaned = _PRIORITY_HEADER_PATTERNS.sub(" ", block)
    cleaned = re.sub(r"\(пункт\s+\d+\s+статьи\s+\d+\s+Кодекса\)", "", cleaned)
    cleaned = re.sub(r"\(Собрание\s+законодательства[^)]+\)", "", cleaned)
    cleaned = re.sub(r"\(далее[^)]+\)", "", cleaned)
    cleaned = re.sub(r"\(при\s+испрашивани[еи][^)]+\)", "", cleaned)
    cleaned = re.sub(r"\(пункт\s+\d+\s+статьи\s+\d+[^)]+\)", "", cleaned)
    cleaned = re.sub(r"\s+", " ", cleaned).strip()
    if len(cleaned) < 3:
        return False
    has_date = bool(re.search(r"\b\d{1,2}[./]\d{1,2}[./]\d{2,4}\b", cleaned))
    has_number_after_no = bool(re.search(r"№\s*([A-Z0-9\-]{4,})", cleaned))
    has_country = bool(
        re.search(r"\bкод\s+страны\s*[:\-]?\s*([A-Z]{2})\b", cleaned, re.IGNORECASE)
    )
    bare = re.findall(r"\b(\d{4,})\b", cleaned)
    has_real_bare = any(
        n not in _NON_DATA_NUMBERS and len(n) >= 4 for n in bare
    )
    return has_date or has_number_after_no or has_country or has_real_bare


def _mark_type_block_has_data(block: str) -> bool:
    if not block:
        return False
    if _MARK_TYPE_OPTION_KEYWORDS.search(block):
        return True
    cleaned = _MARK_TYPE_OPTION_KEYWORDS.sub(" ", block)
    cleaned = re.sub(
        r"Указание,?\s+относящееся\s+к\s+виду\s+знака:?\s*",
        "",
        cleaned,
        flags=re.IGNORECASE,
    )
    cleaned = re.sub(r"\s+", " ", cleaned).strip()
    return len(cleaned) >= 3 and bool(re.search(r"[А-ЯЁA-Za-z0-9]", cleaned))


def _is_valid_country_code(token: str) -> bool:
    return token in _VALID_COUNTRY_CODES


def _clean(text: str) -> str:
    if not text:
        return ""
    text = re.sub(r"-\s*\n", "", text)
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def _split_inid_blocks(text: str) -> list[tuple[str, str]]:
    matches = list(_INID_RE.finditer(text))
    if not matches:
        return [("", text)]
    blocks: list[tuple[str, str]] = []
    if matches[0].start() > 0:
        blocks.append(("", text[: matches[0].start()].strip()))
    for i, m in enumerate(matches):
        code = m.group(1)
        start = m.end()
        end = matches[i + 1].start() if i + 1 < len(matches) else len(text)
        blocks.append((code, text[start:end].strip()))
    return blocks


def _detect_mark_type(text: str) -> tuple[str | None, str | None]:
    """Сопоставляет текст о типе знака с каноническим значением.

    Возвращает (canonical_type, raw_match). При нескольких совпадениях
    отдаёт приоритет «специфическим» типам (3d, sound, ...) перед общими
    (word, figurative, combined).
    """
    if not text:
        return None, None
    text_low = text.lower()
    matched = []  # (priority, canonical, raw)
    for kwd, canon in _MARK_TYPE_MAP.items():
        if kwd in text_low:
            prio = _MARK_TYPE_ORDER.index(canon) if canon in _MARK_TYPE_ORDER else 99
            matched.append((prio, canon, kwd))
    if not matched:
        m = _MARK_TYPE_OPTION_KEYWORDS.search(text)
        return None, m.group(1) if m else None
    matched.sort(key=lambda t: t[0], reverse=True)
    return matched[0][1], matched[0][2]
@dataclass
class ParsedApplication:
    client: dict[str, Any] = field(default_factory=dict)
    application: dict[str, Any] = field(default_factory=dict)
    representative: dict[str, Any] = field(default_factory=dict)
    priority: dict[str, Any] = field(default_factory=dict)
    confidence: dict[str, float] = field(default_factory=dict)
    warnings: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "client": self.client,
            "application": self.application,
            "representative": self.representative,
            "priority": self.priority,
            "confidence": self.confidence,
            "warnings": self.warnings,
        }
class ApplicationPdfParser:
    """Извлекает данные из заполненной формы заявки (PDF/DOCX) без LLM."""

    def parse(self, raw_text: str) -> ParsedApplication:
        text = _clean(raw_text)
        parsed = ParsedApplication()
        self._parse_client(text, parsed)
        self._parse_representative(text, parsed)
        self._parse_correspondence(text, parsed)
        self._parse_mark(text, parsed)
        self._parse_classes(text, parsed)
        self._parse_priority(text, parsed)
        self._parse_filing_date(text, parsed)
        self._build_warnings(parsed)
        return parsed

    # ------------------------------------------------------------------
    # Клиент (731)
    # ------------------------------------------------------------------

    def _parse_client(self, text: str, parsed: ParsedApplication) -> None:
        blocks = dict(_split_inid_blocks(text))
        # В бланке Роспатента (731) содержит наименование, а ИНН/ОГРН/КПП/
        # адрес/код страны/контакты идут сразу за ним, до (740) или до
        # следующего INID-кода. Поэтому склеиваем всё от (731) до первого
        # следующего INID-кода, который НЕ является (732).
        ordered = list(_INID_RE.finditer(text))
        client_block_parts: list[str] = []
        started = False
        for i, m in enumerate(ordered):
            code = m.group(1)
            start = m.start()
            end = ordered[i + 1].start() if i + 1 < len(ordered) else len(text)
            if code == "731":
                client_block_parts.append(text[start:end])
                started = True
                continue
            if started and code not in ("732",):
                break
            if started and code == "732":
                client_block_parts.append(text[start:end])
        client_block = "\n".join(client_block_parts).strip()
        if not client_block:
            return

        org_match = _ORG_FORM_RE.search(client_block)
        if org_match:
            start = client_block.rfind("\n", 0, org_match.start()) + 1
            end_lf = client_block.find("\n", org_match.end())
            end = end_lf if end_lf != -1 else len(client_block)
            full_name = client_block[start:end].strip(" ,.;:")
            full_name = _INID_RE.sub("", full_name).strip(" ,.;:")
            if not _CLIENT_HEADER_PATTERNS.search(full_name):
                parsed.client["full_name_or_company_name"] = full_name
                parsed.confidence["client.full_name_or_company_name"] = 0.92

        addr_match = re.search(
            r"\b(\d{6})\s*,\s*([^,\n]+(?:,\s*[^,\n]+){0,3})",
            client_block,
        )
        if addr_match:
            full_name = parsed.client.get("full_name_or_company_name", "")
            addr = f"{addr_match.group(1)}, {addr_match.group(2).strip()}"
            if full_name and full_name in addr:
                addr = addr.replace(full_name, "").strip(" ,")
            if addr and addr != full_name:
                parsed.client["address"] = addr
                parsed.confidence["client.address"] = 0.85

        inn_m = _INN_RE.search(client_block)
        if inn_m:
            parsed.client["inn"] = inn_m.group(1)
            parsed.confidence["client.inn"] = 0.95

        ogrn_m = _OGRN_RE.search(client_block)
        if ogrn_m:
            parsed.client["ogrn_or_ogrnip"] = ogrn_m.group(1)
            parsed.confidence["client.ogrn_or_ogrnip"] = 0.95

        kpp_m = _KPP_RE.search(client_block)
        if kpp_m:
            parsed.client["kpp"] = kpp_m.group(1)
            parsed.confidence["client.kpp"] = 0.90

        code_m = re.search(
            r"код\s+страны[^a-zA-Z]{0,40}?([A-Z]{2})\b",
            client_block,
            re.IGNORECASE,
        )
        if code_m and _is_valid_country_code(code_m.group(1)):
            parsed.client["country_code"] = code_m.group(1)
            parsed.confidence["client.country_code"] = 0.85

        phones = re.findall(
            r"(?:тел(?:ефон)?\.?|факс)[:\s]*([+\d()\-\s]{6,})",
            client_block,
            re.IGNORECASE,
        )
        if phones:
            parsed.client["phone"] = phones[0].strip()
            parsed.confidence["client.phone"] = 0.85

        em_m = _EMAIL_RE.search(client_block)
        if em_m:
            parsed.client["email"] = em_m.group(0)
            parsed.confidence["client.email"] = 0.95
# ------------------------------------------------------------------
    # Представитель (740)
    # ------------------------------------------------------------------

    def _parse_representative(self, text: str, parsed: ParsedApplication) -> None:
        blocks = dict(_split_inid_blocks(text))
        block = blocks.get("740", "")
        if not block:
            return

        fio = re.search(
            r"([А-ЯЁ][а-яё]+(?:\s+[А-ЯЁ][а-яё]+){1,3})\s*,?\s*(патентн\w*\s+поверенн\w*|иной\s+представитель)?",
            block,
        )
        if fio:
            parsed.representative["full_name"] = fio.group(1).strip()
            parsed.confidence["representative.full_name"] = 0.85
            role = fio.group(2)
            if role:
                role_clean = role.lower()
                if "патент" in role_clean:
                    parsed.representative["role"] = "Патентный поверенный"
                else:
                    parsed.representative["role"] = "Иной представитель"
                parsed.confidence["representative.role"] = 0.85

        reg_m = re.search(r"(?:рег\.?\s*№|рег\s*№|№)\s*(\d{2,6})", block)
        if reg_m:
            parsed.representative["patent_attorney_reg_number"] = reg_m.group(1)
            parsed.confidence["representative.patent_attorney_reg_number"] = 0.90

        phone_m = re.search(
            r"тел(?:ефон)?\.?\s*[:\s]*([+\d()\-\s]{6,})",
            block,
            re.IGNORECASE,
        )
        if phone_m:
            parsed.representative["phone"] = phone_m.group(1).strip()
            parsed.confidence["representative.phone"] = 0.80

        em_m = _EMAIL_RE.search(block)
        if em_m:
            parsed.representative["email"] = em_m.group(0)
            parsed.confidence["representative.email"] = 0.90

    # ------------------------------------------------------------------
    # Адрес для переписки (750)
    # ------------------------------------------------------------------

    def _parse_correspondence(self, text: str, parsed: ParsedApplication) -> None:
        blocks = dict(_split_inid_blocks(text))
        block = blocks.get("750", "")
        if not block:
            return
        addr_m = re.search(
            r"\b(\d{6})\s*,\s*([^,\n]+(?:,\s*[^,\n]+){0,3})",
            block,
        )
        if addr_m:
            addr = f"{addr_m.group(1)}, {addr_m.group(2).strip()}"
            parsed.application["correspondence_address"] = addr
            parsed.confidence["application.correspondence_address"] = 0.85
# ------------------------------------------------------------------
    # Обозначение и тип (540, 541, 550, 571)
    # ------------------------------------------------------------------

    def _parse_mark(self, text: str, parsed: ParsedApplication) -> None:
        blocks = dict(_split_inid_blocks(text))
        block540 = blocks.get("540", "")
        block571 = blocks.get("571", "")
        block541 = blocks.get("541", "")
        block550 = blocks.get("550", "")

        mark_text = None
        if block540:
            qm = _MARK_NAME_QUOTED_RE.search(block540)
            if qm:
                mark_text = qm.group(1).strip()
            else:
                first_line = next(
                    (ln.strip(" ,.:;") for ln in block540.splitlines()
                     if ln.strip() and not _FILING_DATE_KEYWORDS.search(ln)
                     and len(ln.strip()) > 1),
                    None,
                )
                if first_line:
                    mark_text = first_line
        if mark_text:
            parsed.application["mark_name"] = mark_text
            parsed.confidence["application.mark_name"] = 0.90
            parsed.application["mark_text"] = mark_text
            parsed.confidence["application.mark_text"] = 0.90

        type_source = block541 or block550 or block540
        if type_source and _mark_type_block_has_data(type_source):
            canonical, raw = _detect_mark_type(type_source)
            if canonical:
                parsed.application["mark_type"] = canonical
                parsed.confidence["application.mark_type"] = 0.85
            if raw:
                parsed.application["mark_type_raw"] = raw
                parsed.confidence["application.mark_type_raw"] = 0.85

        if block571:
            desc_lines = [
                ln.strip() for ln in block571.splitlines()
                if ln.strip() and not _MARK_TYPE_OPTION_KEYWORDS.search(ln)
            ]
            if desc_lines:
                desc = " ".join(desc_lines[:3]).strip()
                if desc and len(desc) >= 3:
                    parsed.application["description_of_mark"] = desc
                    parsed.confidence["application.description_of_mark"] = 0.80

        block591 = blocks.get("591", "") or blocks.get("546", "")
        if block591:
            color_lines = [
                ln.strip() for ln in block591.splitlines()
                if ln.strip() and not _INID_RE.match(ln)
            ]
            if color_lines:
                parsed.application["colors_claimed"] = "; ".join(color_lines[:5])
                parsed.confidence["application.colors_claimed"] = 0.80

    # ------------------------------------------------------------------
    # Классы МКТУ (511)
    # ------------------------------------------------------------------

    def _parse_classes(self, text: str, parsed: ParsedApplication) -> None:
        blocks = dict(_split_inid_blocks(text))
        block = blocks.get("511", "")
        if not block:
            return
        classes = {}
        for m in re.finditer(r"\b(\d{1,2})\s+([^\n]+)", block):
            cls_num = int(m.group(1))
            if 1 <= cls_num <= 45:
                classes.setdefault(cls_num, []).append(m.group(2).strip())
        if classes:
            parsed.application["mktu_classes"] = sorted(classes.keys())
            parsed.confidence["application.mktu_classes"] = 0.95
            lines = []
            for cls in sorted(classes.keys()):
                lines.append(f"Класс {cls}: " + "; ".join(classes[cls]))
            parsed.application["goods_services_raw"] = "\n".join(lines)
            parsed.confidence["application.goods_services_raw"] = 0.95
            desc = re.sub(r"\s+", " ",
                          "; ".join(classes[s][0] for s in sorted(classes))).strip()
            if desc:
                parsed.application["goods_services_description"] = desc[:1000]
                parsed.confidence["application.goods_services_description"] = 0.85
# ------------------------------------------------------------------
    # Приоритет (310, 320, 330, 641, 151)
    # ------------------------------------------------------------------

    def _parse_priority(self, text: str, parsed: ParsedApplication) -> None:
        blocks = dict(_split_inid_blocks(text))
        date = None
        num = None
        country = None
        for code in ("310", "320", "641"):
            block = blocks.get(code, "")
            if not block or not _priority_block_has_data(block):
                continue
            d = re.search(r"(\d{1,2}[./]\d{1,2}[./]\d{2,4})", block)
            if d and not date:
                date = d.group(1)
            n = re.search(r"№\s*([A-Z0-9][A-Z0-9\-\.\s/]{3,15})", block)
            if n:
                cleaned = n.group(1).strip().strip(". ")
                cleaned = re.sub(r"\s+", "", cleaned)
                if cleaned and cleaned not in _NON_DATA_NUMBERS and len(cleaned) >= 4:
                    num = cleaned
            c = re.search(r"\(([A-Z]{2})\)", block)
            if not c:
                c = re.search(
                    r"\bкод\s+страны\s*[:\-]?\s*([A-Z]{2})\b",
                    block,
                    re.IGNORECASE,
                )
            if c and _is_valid_country_code(c.group(1)):
                country = c.group(1)
            if date or num or country:
                break

        block151 = blocks.get("151", "")
        if block151 and _priority_block_has_data(block151):
            m = re.search(r"(\d{6,})", block151)
            if m:
                parsed.priority["international_registration_number"] = m.group(1)
                parsed.confidence["priority.international_registration_number"] = 0.90

        if date or num or country:
            if date:
                parsed.priority["priority_filing_date"] = date
                parsed.confidence["priority.priority_filing_date"] = 0.85
            if num:
                parsed.priority["priority_earliest_application_number"] = num
                parsed.confidence["priority.priority_earliest_application_number"] = 0.85
            if country:
                parsed.priority["priority_country_code"] = country
                parsed.confidence["priority.priority_country_code"] = 0.85

    # ------------------------------------------------------------------
    # Дата подачи / поступления (210, 220)
    # ------------------------------------------------------------------

    def _parse_filing_date(self, text: str, parsed: ParsedApplication) -> None:
        blocks = dict(_split_inid_blocks(text))
        for code, key in (("210", "filing_date_reception"), ("220", "filing_date")):
            block = blocks.get(code, "")
            if not block:
                continue
            m = re.search(r"(\d{1,2}[./]\d{1,2}[./]\d{2,4})", block)
            if m:
                parsed.application[key] = m.group(1)
                parsed.confidence[f"application.{key}"] = 0.85

    # ------------------------------------------------------------------
    # Warnings
    # ------------------------------------------------------------------

    def _build_warnings(self, parsed: ParsedApplication) -> None:
        c = parsed.client
        if not c.get("full_name_or_company_name"):
            parsed.warnings.append(
                "Не извлечено полное наименование заявителя (блок 731)"
            )
        if not c.get("inn"):
            parsed.warnings.append("Не извлечён ИНН заявителя")
        if not c.get("address"):
            parsed.warnings.append("Не извлечён адрес заявителя (блок 731)")
        a = parsed.application
        if not a.get("mark_name"):
            parsed.warnings.append(
                "Не извлечено обозначение (название знака, блок 540/571)"
            )
        if not a.get("mktu_classes"):
            parsed.warnings.append("Не извлечены классы МКТУ (блок 511)")
        if parsed.representative and not parsed.representative.get(
            "patent_attorney_reg_number"
        ):
            parsed.warnings.append(
                "Не извлечён регистрационный номер пат. поверенного (блок 740)"
            )
        if parsed.representative and not parsed.representative.get("full_name"):
            parsed.warnings.append("Не извлечено ФИО представителя (блок 740)")
        if (
            parsed.priority
            and not parsed.priority.get("priority_country_code")
            and (
                parsed.priority.get("priority_filing_date")
                or parsed.priority.get("priority_earliest_application_number")
            )
        ):
            parsed.warnings.append(
                "Указаны реквизиты приоритета, но не извлечён код страны"
            )

    # ------------------------------------------------------------------
    # Legacy-проекция (applicant/mark/classes)
    # ------------------------------------------------------------------

    @staticmethod
    def _project_legacy(parsed: ParsedApplication) -> dict[str, Any]:
        c = parsed.client or {}
        a = parsed.application or {}
        r = parsed.representative or {}
        p = parsed.priority or {}

        applicant = {
            "name": c.get("full_name_or_company_name"),
            "short_name": c.get("short_name"),
            "inn": c.get("inn"),
            "ogrn": c.get("ogrn_or_ogrnip"),
            "kpp": c.get("kpp"),
            "address": c.get("address"),
            "country_code": c.get("country_code"),
            "country": c.get("country"),
            "phone": c.get("phone"),
            "email": c.get("email"),
            "representative": (
                {
                    "full_name": r.get("full_name"),
                    "role": r.get("role"),
                    "reg_number": r.get("patent_attorney_reg_number"),
                    "phone": r.get("phone"),
                    "email": r.get("email"),
                    "address": r.get("address"),
                }
                if r
                else None
            ),
        }
        mark = {
            "text": a.get("mark_name") or a.get("mark_text"),
            "mark_name": a.get("mark_name"),
            "type": a.get("mark_type"),
            "type_raw": a.get("mark_type_raw"),
            "description": a.get("description_of_mark"),
            "colors_claimed": a.get("colors_claimed"),
            "transliteration": a.get("transliteration"),
            "translation": a.get("translation"),
            "image_file_id": a.get("mark_image_file_id"),
        }
        out: dict[str, Any] = {
            "applicant": applicant,
            "mark": mark,
            "classes": a.get("mktu_classes") or [],
            "goods_services_description": a.get("goods_services_description")
            or a.get("goods_services_raw"),
            "goods_services_raw": a.get("goods_services_raw"),
            "correspondence_address": a.get("correspondence_address"),
            "contact_phone": a.get("contact_phone"),
            "contact_fax": a.get("contact_fax"),
            "contact_email": a.get("contact_email"),
            "filing_date": a.get("filing_date"),
            "filing_date_reception": a.get("filing_date_reception"),
            "priority_date": p.get("priority_filing_date"),
            "priority_earliest_application_number": p.get(
                "priority_earliest_application_number"
            ),
            "priority_country_code": p.get("priority_country_code"),
            "international_registration_number": p.get(
                "international_registration_number"
            ),
        }
        cleaned: dict[str, Any] = {}
        for k, v in out.items():
            if v is None:
                continue
            if isinstance(v, dict) and not v:
                continue
            cleaned[k] = v
        return cleaned
class ApplicationPdfParserAgent(BaseAgent):
    """Агент-обёртка над :class:`ApplicationPdfParser`.

    Вход input_data:
        raw_text         : str   — текст, извлечённый из PDF/DOCX
        source_filename  : str | None
        legacy_schema    : bool  — добавить legacy-проекцию в findings
        use_llm          : bool  — LLM-fallback для пустых полей

    Выход StructuredAgentOutput:
        findings["parsed"]   : полный результат парсера (новая схема)
        findings["legacy"]   : legacy-проекция (если legacy_schema=True)
        confidence           : среднее по заполненным полям
        next_actions         : ["request_missing_data_from_client"]
                               если есть критические пропуски.
    """

    agent_type = "intake.application_parser"
    input_schema = {
        "type": "object",
        "required": ["raw_text"],
        "properties": {
            "raw_text": {"type": "string"},
            "source_filename": {"type": ["string", "null"]},
            "legacy_schema": {"type": "boolean", "default": False},
            "use_llm": {"type": "boolean", "default": False},
        },
    }

    def __init__(self, prompt_registry, llm_provider) -> None:
        super().__init__(prompt_registry=prompt_registry, llm_provider=llm_provider)
        self._parser = ApplicationPdfParser()
async def execute(self, input_data: dict) -> StructuredAgentOutput:
        raw_text: str = (input_data.get("raw_text") or "")
        source_filename = input_data.get("source_filename")
        legacy_schema: bool = bool(input_data.get("legacy_schema", False))
        use_llm: bool = bool(input_data.get("use_llm", False))

        if not raw_text.strip():
            return StructuredAgentOutput(
                error="raw_text is empty",
                summary="Пустой входной текст: нечего парсить",
                human_review_required=True,
                next_actions=["request_missing_data_from_client"],
            )

        try:
            parsed: ParsedApplication = self._parser.parse(raw_text)
        except Exception as exc:
            logger.exception("ApplicationPdfParser.parse failed")
            return StructuredAgentOutput(
                error=f"parser error: {exc}",
                summary=f"Ошибка парсера заявки: {exc}",
                human_review_required=True,
                next_actions=["retry_parsing", "request_human_review"],
            )

        llm_filled = []
        if use_llm:
            llm_filled = await self._llm_fill_gaps(raw_text, parsed)
            if llm_filled:
                parsed.warnings.append(
                    "LLM-fallback заполнил поля: " + ", ".join(llm_filled)
                )

        conf_values = [
            v for v in parsed.confidence.values() if isinstance(v, (int, float))
        ]
        avg_conf = (sum(conf_values) / len(conf_values)) if conf_values else 0.0

        findings = {
            "parsed": {
                **parsed.to_dict(),
                "source_filename": source_filename,
                "source_text_length": len(raw_text),
                "extraction_method": (
                    "heuristic+llm_fallback" if use_llm else "heuristic"
                ),
            },
        }
        if legacy_schema:
            findings["legacy"] = ApplicationPdfParser._project_legacy(parsed)

        blocking = []
        c = parsed.client
        a = parsed.application
        if not c.get("full_name_or_company_name"):
            blocking.append("client.full_name_or_company_name")
        if not c.get("inn"):
            blocking.append("client.inn")
        if not c.get("address"):
            blocking.append("client.address")
        if not a.get("mark_name"):
            blocking.append("application.mark_name")
        if not a.get("mktu_classes"):
            blocking.append("application.mktu_classes")

        return StructuredAgentOutput(
            summary=(
                f"Распознано полей: {len(conf_values)} "
                f"(ср. уверенность {avg_conf:.2f}). "
                f"Предупреждения: {len(parsed.warnings)}."
            ),
            findings=findings,
            evidence=[
                {
                    "source_filename": source_filename,
                    "text_length": len(raw_text),
                    "extracted_fields": list(parsed.confidence.keys()),
                }
            ],
            missing_info=[
                {"field": f, "reason": "не извлечено из бланка"}
                for f in blocking
            ],
            confidence=round(avg_conf, 3),
            human_review_required=len(blocking) > 0,
            next_actions=(
                ["request_missing_data_from_client"] if blocking
                else ["proceed_to_normalization"]
            ),
        )
async def _llm_fill_gaps(
        self, raw_text: str, parsed: ParsedApplication
    ) -> list[str]:
        """Точечный LLM-fallback для полей, не извлечённых эвристикой."""
        try:
            gaps = {
                "client.full_name_or_company_name": not parsed.client.get(
                    "full_name_or_company_name"
                ),
                "client.address": not parsed.client.get("address"),
                "client.inn": not parsed.client.get("inn"),
                "client.ogrn_or_ogrnip": not parsed.client.get("ogrn_or_ogrnip"),
                "client.country_code": not parsed.client.get("country_code"),
                "application.mark_name": not parsed.application.get("mark_name"),
                "application.mark_type": not parsed.application.get("mark_type"),
                "application.mktu_classes": not parsed.application.get("mktu_classes"),
            }
            missing = [k for k, v in gaps.items() if v]
            if not missing:
                return []
            already = {
                "client.full_name_or_company_name": parsed.client.get(
                    "full_name_or_company_name"
                ),
                "application.mark_name": parsed.application.get("mark_name"),
                "application.mktu_classes": parsed.application.get("mktu_classes"),
            }
            result = await self._call_llm_structured(
                "intake.application_pdf_parser_fill_gaps",
                {
                    "raw_text": raw_text[:6000],
                    "missing_fields": missing,
                    "already_extracted": {k: v for k, v in already.items() if v},
                },
            )
            filled = []
            data = result.get("fields") or {}
            if not isinstance(data, dict):
                return filled

            if (
                data.get("client.full_name_or_company_name")
                and not parsed.client.get("full_name_or_company_name")
            ):
                parsed.client["full_name_or_company_name"] = str(
                    data["client.full_name_or_company_name"]
                )
                parsed.confidence["client.full_name_or_company_name"] = 0.80
                filled.append("client.full_name_or_company_name")
            if data.get("client.address") and not parsed.client.get("address"):
                parsed.client["address"] = str(data["client.address"])
                parsed.confidence["client.address"] = 0.80
                filled.append("client.address")
            if data.get("client.inn") and not parsed.client.get("inn"):
                parsed.client["inn"] = str(data["client.inn"])
                parsed.confidence["client.inn"] = 0.85
                filled.append("client.inn")
            if (
                data.get("client.ogrn_or_ogrnip")
                and not parsed.client.get("ogrn_or_ogrnip")
            ):
                parsed.client["ogrn_or_ogrnip"] = str(data["client.ogrn_or_ogrnip"])
                parsed.confidence["client.ogrn_or_ogrnip"] = 0.85
                filled.append("client.ogrn_or_ogrnip")
            if (
                data.get("client.country_code")
                and not parsed.client.get("country_code")
            ):
                parsed.client["country_code"] = str(
                    data["client.country_code"]
                ).upper()[:2]
                parsed.confidence["client.country_code"] = 0.80
                filled.append("client.country_code")
            if (
                data.get("application.mark_name")
                and not parsed.application.get("mark_name")
            ):
                parsed.application["mark_name"] = str(
                    data["application.mark_name"]
                )
                parsed.confidence["application.mark_name"] = 0.80
                filled.append("application.mark_name")
            if (
                data.get("application.mark_type")
                and not parsed.application.get("mark_type")
            ):
                parsed.application["mark_type"] = str(
                    data["application.mark_type"]
                )
                parsed.confidence["application.mark_type"] = 0.80
                filled.append("application.mark_type")
            if (
                data.get("application.mktu_classes")
                and not parsed.application.get("mktu_classes")
            ):
                val = data["application.mktu_classes"]
                if isinstance(val, list):
                    cls_list = [int(x) for x in val if str(x).isdigit()]
                else:
                    cls_list = [
                        int(x)
                        for x in str(val).split(",")
                        if x.strip().isdigit()
                    ]
                cls_list = [c for c in cls_list if 1 <= c <= 45]
                if cls_list:
                    parsed.application["mktu_classes"] = sorted(set(cls_list))
                    parsed.confidence["application.mktu_classes"] = 0.80
                    filled.append("application.mktu_classes")
            return filled
        except Exception as exc:
            logger.warning("LLM fallback for application parser failed: %s", exc)
            return []


__all__ = [
    "ApplicationPdfParser",
    "ParsedApplication",
    "ApplicationPdfParserAgent",
]
