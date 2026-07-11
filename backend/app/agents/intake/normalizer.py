"""
ClientDataNormalizerAgent — normalises applicant names, addresses,
phone numbers, and handles transliteration between Cyrillic and Latin.
"""
from __future__ import annotations

import logging
import re

from app.agents.base import BaseAgent, StructuredAgentOutput

logger = logging.getLogger(__name__)

# -------------------------------------------------------------------------
# Normalisation helpers
# -------------------------------------------------------------------------

_PHONE_RE = re.compile(r"[\s\-\(\)]+")


def _normalize_phone(phone: str) -> str:
    digits = re.sub(r"\D", "", phone)
    if digits.startswith("8") and len(digits) == 11:
        digits = "7" + digits[1:]
    if len(digits) == 11 and digits.startswith("7"):
        return f"+7({digits[1:4]}){digits[4:7]}-{digits[7:9]}-{digits[9:11]}"
    return phone  # return as-is if unrecognized


def _normalize_inn(inn: str) -> str:
    return re.sub(r"\D", "", inn)


def _normalize_ogrn(ogrn: str) -> str:
    return re.sub(r"\D", "", ogrn)


def _normalize_address(address: str) -> str:
    """
    Basic address normalisation:
    - Collapse multiple spaces
    - Ensure comma after postcode
    - Expand common abbreviations
    """
    addr = re.sub(r"\s+", " ", address.strip())
    # Add comma after 6-digit postcode at start
    addr = re.sub(r"^(\d{6})\s", r"\1, ", addr)
    # Normalise common abbreviations
    addr = re.sub(r"\bг\s+", "г. ", addr)
    addr = re.sub(r"\bул\s+", "ул. ", addr)
    addr = re.sub(r"\bд\s+", "д. ", addr)
    addr = re.sub(r"\bкв\s+", "кв. ", addr)
    return addr


def _normalize_org_name(name: str) -> str:
    """Ensure OOO/AO/PAO is properly formatted."""
    name = name.strip()
    # Normalize common Russian org type abbreviations
    name = re.sub(r'\bООО\s*"?', 'ООО "', name)
    name = re.sub(r'\bАО\s*"?', 'АО "', name)
    name = re.sub(r'\bПАО\s*"?', 'ПАО "', name)
    # Ensure closing quote
    if (
        ('ООО "' in name or 'АО "' in name or 'ПАО "' in name)
        and not name.endswith('"')
        and not name.endswith('»')
    ):
        name += '"'
    return name


_TRANSLIT_TABLE = {
    "a": "а", "b": "б", "v": "в", "g": "г", "d": "д",
    "e": "е", "z": "з", "i": "и", "y": "й", "k": "к",
    "l": "л", "m": "м", "n": "н", "o": "о", "p": "п",
    "r": "р", "s": "с", "t": "т", "u": "у", "f": "ф",
    "h": "х", "c": "ц", "j": "ж", "q": "к", "w": "в",
    "x": "кс",
}


def _detect_script(text: str) -> str:
    """Return 'cyrillic', 'latin', or 'mixed'."""
    cyr = sum(1 for c in text if "\u0400" <= c <= "\u04FF")
    lat = sum(1 for c in text if c.isalpha() and c.isascii())
    if cyr > 0 and lat > 0:
        return "mixed"
    if cyr > 0:
        return "cyrillic"
    return "latin"


# -------------------------------------------------------------------------
# Agent
# -------------------------------------------------------------------------


class ClientDataNormalizerAgent(BaseAgent):
    """
    Normalises applicant and mark data:
    - Phone numbers: → +7(XXX)XXX-XX-XX
    - INN/OGRN: strip non-digits
    - Address: postcode comma, abbreviation expansion
    - Organisation name: consistent quote style
    - Detects script of mark text (cyrillic/latin/mixed)

    Input dict keys:
        application_data (dict): Raw application fields

    Output findings:
        normalized_data, corrections_made, script_info
    """

    agent_type = "intake.normalizer"

    input_schema = {
        "type": "object",
        "required": ["application_data"],
        "properties": {
            "application_data": {"type": "object"},
        },
    }

    async def execute(self, input_data: dict) -> StructuredAgentOutput:
        raw = input_data.get("application_data", {})
        import copy

        normalized = copy.deepcopy(raw)
        corrections: list[dict] = []

        # Normalise applicant fields
        applicant = normalized.get("applicant", {})
        if isinstance(applicant, dict):
            if applicant.get("phone"):
                orig = applicant["phone"]
                applicant["phone"] = _normalize_phone(orig)
                if applicant["phone"] != orig:
                    corrections.append(
                        {"field": "applicant.phone", "original": orig, "normalized": applicant["phone"]}
                    )

            if applicant.get("inn"):
                orig = applicant["inn"]
                applicant["inn"] = _normalize_inn(orig)
                if applicant["inn"] != orig:
                    corrections.append(
                        {"field": "applicant.inn", "original": orig, "normalized": applicant["inn"]}
                    )

            if applicant.get("ogrn"):
                orig = applicant["ogrn"]
                applicant["ogrn"] = _normalize_ogrn(orig)
                if applicant["ogrn"] != orig:
                    corrections.append(
                        {"field": "applicant.ogrn", "original": orig, "normalized": applicant["ogrn"]}
                    )

            if applicant.get("address"):
                orig = applicant["address"]
                applicant["address"] = _normalize_address(orig)
                if applicant["address"] != orig:
                    corrections.append(
                        {"field": "applicant.address", "original": orig, "normalized": applicant["address"]}
                    )

            if applicant.get("name"):
                orig = applicant["name"]
                applicant["name"] = _normalize_org_name(orig)
                if applicant["name"] != orig:
                    corrections.append(
                        {"field": "applicant.name", "original": orig, "normalized": applicant["name"]}
                    )

            normalized["applicant"] = applicant

        # Detect mark script
        mark = normalized.get("mark", {})
        script_info: dict = {}
        if isinstance(mark, dict) and mark.get("text"):
            script = _detect_script(mark["text"])
            script_info = {
                "mark_text": mark["text"],
                "script": script,
                "transliteration_recommended": script == "latin",
                "phonetic_analysis_needed": script in ("cyrillic", "mixed"),
            }

        findings = {
            "normalized_data": normalized,
            "corrections_made": corrections,
            "corrections_count": len(corrections),
            "script_info": script_info,
        }

        summary = (
            f"Нормализация данных завершена. "
            f"Исправлений: {len(corrections)}. "
            f"Скрипт обозначения: {script_info.get('script', 'н/д')}."
        )

        return StructuredAgentOutput(
            summary=summary,
            findings=findings,
            confidence=0.97,
            evidence=[{"corrections": corrections}],
            next_actions=["proceed_to_legal_review"],
        )
