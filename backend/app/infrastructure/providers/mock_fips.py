"""
Mock FIPS (Роспатент) provider for development and testing.

Includes:
  - SeededRegistryDataset: 50+ realistic Russian trademark entries
  - Fuzzy text similarity search
  - Basic Russian phonetic matching
  - FakeStatusLifecycle that progresses through realistic stages
"""
from __future__ import annotations

import hashlib
import re
import uuid
from datetime import datetime, timedelta
from typing import Any

from app.infrastructure.providers.base import (
    ExternalStatusResult,
    RegistryRecord,
    SearchQuery,
    SubmissionPayload,
    SubmissionResult,
)

# ---------------------------------------------------------------------------
# Seeded dataset — 55 realistic Russian trademark entries
# ---------------------------------------------------------------------------

_DATASET: list[dict[str, Any]] = [
    # ── Financial ──────────────────────────────────────────────────────────
    {
        "record_id": "RU0001001",
        "mark_text": "АЛЬФА-БАНК",
        "mark_type": "словесное",
        "owner": 'АО "АЛЬФА-БАНК"',
        "classes": [36, 35],
        "status": "registered",
        "filing_date": "1995-03-10",
        "registration_date": "1996-06-20",
        "image_url": None,
    },
    {
        "record_id": "RU0001002",
        "mark_text": "СБЕР",
        "mark_type": "словесное",
        "owner": 'ПАО "Сбербанк России"',
        "classes": [36, 35, 38, 42],
        "status": "registered",
        "filing_date": "2020-08-01",
        "registration_date": "2021-03-15",
        "image_url": None,
    },
    {
        "record_id": "RU0001003",
        "mark_text": "СБЕРБАНК",
        "mark_type": "словесное",
        "owner": 'ПАО "Сбербанк России"',
        "classes": [36, 35, 38],
        "status": "registered",
        "filing_date": "1991-11-05",
        "registration_date": "1993-04-12",
        "image_url": None,
    },
    {
        "record_id": "RU0001004",
        "mark_text": "ВТБ",
        "mark_type": "словесное",
        "owner": 'ПАО "Банк ВТБ"',
        "classes": [36, 35],
        "status": "registered",
        "filing_date": "2002-05-20",
        "registration_date": "2003-09-18",
        "image_url": None,
    },
    {
        "record_id": "RU0001005",
        "mark_text": "ТИНЬКОФФ",
        "mark_type": "словесное",
        "owner": 'АО "Тинькофф Банк"',
        "classes": [36, 35, 9],
        "status": "registered",
        "filing_date": "2006-07-14",
        "registration_date": "2007-12-02",
        "image_url": None,
    },
    {
        "record_id": "RU0001006",
        "mark_text": "ГАЗПРОМБАНК",
        "mark_type": "словесное",
        "owner": 'АО "Газпромбанк"',
        "classes": [36, 35],
        "status": "registered",
        "filing_date": "1999-02-22",
        "registration_date": "2000-08-30",
        "image_url": None,
    },
    # ── Technology & Internet ───────────────────────────────────────────────
    {
        "record_id": "RU0002001",
        "mark_text": "ЯНДЕКС",
        "mark_type": "словесное",
        "owner": 'ООО "Яндекс"',
        "classes": [35, 38, 42, 9],
        "status": "registered",
        "filing_date": "2000-01-17",
        "registration_date": "2001-05-29",
        "image_url": None,
    },
    {
        "record_id": "RU0002002",
        "mark_text": "ЯНДЕКС.ТАКСИ",
        "mark_type": "словесное",
        "owner": 'ООО "Яндекс"',
        "classes": [39, 35],
        "status": "registered",
        "filing_date": "2011-10-03",
        "registration_date": "2012-11-15",
        "image_url": None,
    },
    {
        "record_id": "RU0002003",
        "mark_text": "ЯНДЕКС.МАРКЕТ",
        "mark_type": "словесное",
        "owner": 'ООО "Яндекс"',
        "classes": [35, 38],
        "status": "registered",
        "filing_date": "2002-03-01",
        "registration_date": "2003-07-11",
        "image_url": None,
    },
    {
        "record_id": "RU0002004",
        "mark_text": "MAIL.RU",
        "mark_type": "словесное",
        "owner": 'ООО "ВК"',
        "classes": [38, 42, 35],
        "status": "registered",
        "filing_date": "2000-09-11",
        "registration_date": "2001-12-20",
        "image_url": None,
    },
    {
        "record_id": "RU0002005",
        "mark_text": "ВКонтакте",
        "mark_type": "словесное",
        "owner": 'ООО "ВКонтакте"',
        "classes": [38, 42, 41],
        "status": "registered",
        "filing_date": "2006-11-04",
        "registration_date": "2007-09-28",
        "image_url": None,
    },
    {
        "record_id": "RU0002006",
        "mark_text": "1С",
        "mark_type": "словесное",
        "owner": 'ООО "1С"',
        "classes": [42, 9, 41],
        "status": "registered",
        "filing_date": "1996-04-15",
        "registration_date": "1997-10-07",
        "image_url": None,
    },
    # ── Retail & E-Commerce ─────────────────────────────────────────────────
    {
        "record_id": "RU0003001",
        "mark_text": "ОЗОН",
        "mark_type": "словесное",
        "owner": 'ООО "Интернет Решения"',
        "classes": [35, 39, 38],
        "status": "registered",
        "filing_date": "1998-12-14",
        "registration_date": "1999-11-30",
        "image_url": None,
    },
    {
        "record_id": "RU0003002",
        "mark_text": "WILDBERRIES",
        "mark_type": "словесное",
        "owner": 'ООО "Вайлдберриз"',
        "classes": [35, 39],
        "status": "registered",
        "filing_date": "2004-06-08",
        "registration_date": "2005-10-19",
        "image_url": None,
    },
    {
        "record_id": "RU0003003",
        "mark_text": "ВКУСВИЛЛ",
        "mark_type": "словесное",
        "owner": 'ООО "Вкусвилл"',
        "classes": [35, 30, 29],
        "status": "registered",
        "filing_date": "2012-07-23",
        "registration_date": "2013-11-04",
        "image_url": None,
    },
    {
        "record_id": "RU0003004",
        "mark_text": "МАГНИТ",
        "mark_type": "словесное",
        "owner": 'ПАО "Магнит"',
        "classes": [35, 29, 30],
        "status": "registered",
        "filing_date": "2000-05-16",
        "registration_date": "2001-09-22",
        "image_url": None,
    },
    {
        "record_id": "RU0003005",
        "mark_text": "ПЯТЁРОЧКА",
        "mark_type": "словесное",
        "owner": 'X5 RETAIL GROUP',
        "classes": [35, 29, 30, 31],
        "status": "registered",
        "filing_date": "1999-08-04",
        "registration_date": "2000-11-15",
        "image_url": None,
    },
    {
        "record_id": "RU0003006",
        "mark_text": "ПЕРЕКРЁСТОК",
        "mark_type": "словесное",
        "owner": 'X5 RETAIL GROUP',
        "classes": [35, 29, 30],
        "status": "registered",
        "filing_date": "1999-03-17",
        "registration_date": "2000-06-08",
        "image_url": None,
    },
    {
        "record_id": "RU0003007",
        "mark_text": "ЛЕНТА",
        "mark_type": "словесное",
        "owner": 'ООО "Лента"',
        "classes": [35, 29, 30],
        "status": "registered",
        "filing_date": "2000-02-28",
        "registration_date": "2001-05-14",
        "image_url": None,
    },
    # ── Food & Beverage ─────────────────────────────────────────────────────
    {
        "record_id": "RU0004001",
        "mark_text": "ДОДО ПИЦЦА",
        "mark_type": "словесное",
        "owner": 'ООО "Додо Брэндс"',
        "classes": [43, 30, 35],
        "status": "registered",
        "filing_date": "2011-05-18",
        "registration_date": "2012-09-27",
        "image_url": None,
    },
    {
        "record_id": "RU0004002",
        "mark_text": "DODO PIZZA",
        "mark_type": "словесное",
        "owner": 'ООО "Додо Брэндс"',
        "classes": [43, 30],
        "status": "registered",
        "filing_date": "2011-06-01",
        "registration_date": "2012-10-15",
        "image_url": None,
    },
    {
        "record_id": "RU0004003",
        "mark_text": "БУРГЕР КИНГ",
        "mark_type": "словесное",
        "owner": 'ООО "Бургер Рус"',
        "classes": [43, 30],
        "status": "registered",
        "filing_date": "2009-04-11",
        "registration_date": "2010-08-02",
        "image_url": None,
    },
    {
        "record_id": "RU0004004",
        "mark_text": "ВКУСНО — И ТОЧКА",
        "mark_type": "словесное",
        "owner": 'ООО "Росинтер Ресторантс"',
        "classes": [43, 30],
        "status": "registered",
        "filing_date": "2022-05-25",
        "registration_date": "2022-09-12",
        "image_url": None,
    },
    {
        "record_id": "RU0004005",
        "mark_text": "КОФЕМАНИЯ",
        "mark_type": "словесное",
        "owner": 'ООО "Кофемания"',
        "classes": [43, 30, 41],
        "status": "registered",
        "filing_date": "2001-12-03",
        "registration_date": "2002-11-19",
        "image_url": None,
    },
    # ── Telecom ─────────────────────────────────────────────────────────────
    {
        "record_id": "RU0005001",
        "mark_text": "МЕГАФОН",
        "mark_type": "словесное",
        "owner": 'ПАО "МегаФон"',
        "classes": [38, 35, 42],
        "status": "registered",
        "filing_date": "2002-07-09",
        "registration_date": "2003-11-20",
        "image_url": None,
    },
    {
        "record_id": "RU0005002",
        "mark_text": "МТС",
        "mark_type": "словесное",
        "owner": 'ПАО "МТС"',
        "classes": [38, 35, 36],
        "status": "registered",
        "filing_date": "1995-01-21",
        "registration_date": "1996-04-30",
        "image_url": None,
    },
    {
        "record_id": "RU0005003",
        "mark_text": "БИЛАЙН",
        "mark_type": "словесное",
        "owner": 'ПАО "ВымпелКом"',
        "classes": [38, 35],
        "status": "registered",
        "filing_date": "2005-03-01",
        "registration_date": "2006-07-14",
        "image_url": None,
    },
    {
        "record_id": "RU0005004",
        "mark_text": "ТЕЛЕ2",
        "mark_type": "словесное",
        "owner": 'ООО "Т2 Мобайл"',
        "classes": [38, 35],
        "status": "registered",
        "filing_date": "2003-09-22",
        "registration_date": "2004-12-07",
        "image_url": None,
    },
    # ── Healthcare & Pharma ─────────────────────────────────────────────────
    {
        "record_id": "RU0006001",
        "mark_text": "ИНВИТРО",
        "mark_type": "словесное",
        "owner": 'ООО "ИНВИТРО"',
        "classes": [44, 42],
        "status": "registered",
        "filing_date": "2001-08-30",
        "registration_date": "2002-10-15",
        "image_url": None,
    },
    {
        "record_id": "RU0006002",
        "mark_text": "ГЕМОТЕСТ",
        "mark_type": "словесное",
        "owner": 'ООО "Лабораторная служба Хеликс"',
        "classes": [44, 42],
        "status": "registered",
        "filing_date": "2005-11-14",
        "registration_date": "2007-01-29",
        "image_url": None,
    },
    {
        "record_id": "RU0006003",
        "mark_text": "ЭВАЛАР",
        "mark_type": "словесное",
        "owner": 'ЗАО "Эвалар"',
        "classes": [5, 44],
        "status": "registered",
        "filing_date": "1998-06-04",
        "registration_date": "1999-09-17",
        "image_url": None,
    },
    # ── Auto ────────────────────────────────────────────────────────────────
    {
        "record_id": "RU0007001",
        "mark_text": "АВТОДОК",
        "mark_type": "словесное",
        "owner": 'ООО "Автодок"',
        "classes": [35, 37, 12],
        "status": "registered",
        "filing_date": "2008-03-11",
        "registration_date": "2009-06-25",
        "image_url": None,
    },
    {
        "record_id": "RU0007002",
        "mark_text": "КОЛЁСА",
        "mark_type": "словесное",
        "owner": 'ООО "Медиасистем"',
        "classes": [35, 38],
        "status": "registered",
        "filing_date": "2003-02-14",
        "registration_date": "2004-05-31",
        "image_url": None,
    },
    # ── Delivery ────────────────────────────────────────────────────────────
    {
        "record_id": "RU0008001",
        "mark_text": "СДЭК",
        "mark_type": "словесное",
        "owner": 'ООО "СДЭК-ГЛОБАЛ"',
        "classes": [39, 35],
        "status": "registered",
        "filing_date": "2000-01-25",
        "registration_date": "2001-04-10",
        "image_url": None,
    },
    {
        "record_id": "RU0008002",
        "mark_text": "BOXBERRY",
        "mark_type": "словесное",
        "owner": 'ООО "Боксберри"',
        "classes": [39, 35],
        "status": "registered",
        "filing_date": "2010-06-18",
        "registration_date": "2011-10-04",
        "image_url": None,
    },
    {
        "record_id": "RU0008003",
        "mark_text": "ЯНДЕКС.ДОСТАВКА",
        "mark_type": "словесное",
        "owner": 'ООО "Яндекс"',
        "classes": [39, 35],
        "status": "registered",
        "filing_date": "2018-09-03",
        "registration_date": "2019-11-22",
        "image_url": None,
    },
    # ── Energy & Utilities ──────────────────────────────────────────────────
    {
        "record_id": "RU0009001",
        "mark_text": "ЛУКОЙЛ",
        "mark_type": "словесное",
        "owner": 'ПАО "ЛУКОЙЛ"',
        "classes": [4, 35, 37],
        "status": "registered",
        "filing_date": "1993-07-20",
        "registration_date": "1994-12-05",
        "image_url": None,
    },
    {
        "record_id": "RU0009002",
        "mark_text": "ГАЗПРОМ",
        "mark_type": "словесное",
        "owner": 'ПАО "Газпром"',
        "classes": [4, 37, 35],
        "status": "registered",
        "filing_date": "1992-05-30",
        "registration_date": "1993-10-17",
        "image_url": None,
    },
    # ── Real Estate & Construction ──────────────────────────────────────────
    {
        "record_id": "RU0010001",
        "mark_text": "ИНГРАДА",
        "mark_type": "словесное",
        "owner": 'АО "Инграда"',
        "classes": [36, 37],
        "status": "registered",
        "filing_date": "2015-04-07",
        "registration_date": "2016-08-19",
        "image_url": None,
    },
    {
        "record_id": "RU0010002",
        "mark_text": "ПИК",
        "mark_type": "словесное",
        "owner": 'ПАО "ПИК-специализированный застройщик"',
        "classes": [36, 37, 35],
        "status": "registered",
        "filing_date": "2000-10-12",
        "registration_date": "2001-12-28",
        "image_url": None,
    },
    # ── Education ───────────────────────────────────────────────────────────
    {
        "record_id": "RU0011001",
        "mark_text": "SKYENG",
        "mark_type": "словесное",
        "owner": 'ООО "Скайенг"',
        "classes": [41, 42],
        "status": "registered",
        "filing_date": "2012-11-19",
        "registration_date": "2013-12-31",
        "image_url": None,
    },
    {
        "record_id": "RU0011002",
        "mark_text": "НЕТОЛОГИЯ",
        "mark_type": "словесное",
        "owner": 'ООО "Нетология"',
        "classes": [41, 42, 35],
        "status": "registered",
        "filing_date": "2013-03-25",
        "registration_date": "2014-06-11",
        "image_url": None,
    },
    {
        "record_id": "RU0011003",
        "mark_text": "GEEKBRAINS",
        "mark_type": "словесное",
        "owner": 'ООО "ГикБрейнс"',
        "classes": [41, 42],
        "status": "registered",
        "filing_date": "2014-08-06",
        "registration_date": "2015-11-23",
        "image_url": None,
    },
    # ── Media & Entertainment ───────────────────────────────────────────────
    {
        "record_id": "RU0012001",
        "mark_text": "КИНОПОИСК",
        "mark_type": "словесное",
        "owner": 'ООО "Яндекс.Кинопоиск"',
        "classes": [41, 38],
        "status": "registered",
        "filing_date": "2003-10-29",
        "registration_date": "2004-12-16",
        "image_url": None,
    },
    {
        "record_id": "RU0012002",
        "mark_text": "IVI",
        "mark_type": "словесное",
        "owner": 'ООО "Иви.ру"',
        "classes": [41, 38, 42],
        "status": "registered",
        "filing_date": "2010-02-08",
        "registration_date": "2011-04-27",
        "image_url": None,
    },
    # ── Pending / Expired examples ──────────────────────────────────────────
    {
        "record_id": "RU0013001",
        "mark_text": "ИННОТЕХ",
        "mark_type": "словесное",
        "owner": 'ООО "ИнноТех Лаб"',
        "classes": [42, 9],
        "status": "pending",
        "filing_date": "2024-01-15",
        "registration_date": None,
        "image_url": None,
    },
    {
        "record_id": "RU0013002",
        "mark_text": "ТЕХНОВЕКТОР",
        "mark_type": "словесное",
        "owner": 'ООО "ТехноВектор"',
        "classes": [42, 9, 35],
        "status": "pending",
        "filing_date": "2024-02-20",
        "registration_date": None,
        "image_url": None,
    },
    {
        "record_id": "RU0013003",
        "mark_text": "ЦИФРОГРАД",
        "mark_type": "словесное",
        "owner": 'ООО "ЦифроГрад"',
        "classes": [9, 42],
        "status": "expired",
        "filing_date": "2009-06-10",
        "registration_date": "2010-08-14",
        "image_url": None,
    },
    {
        "record_id": "RU0013004",
        "mark_text": "НАНОТЕК",
        "mark_type": "словесное",
        "owner": 'ООО "НаноТек Системс"',
        "classes": [9, 42, 40],
        "status": "cancelled",
        "filing_date": "2011-01-19",
        "registration_date": "2012-03-05",
        "image_url": None,
    },
    {
        "record_id": "RU0013005",
        "mark_text": "СМАРТ-ТЕХ",
        "mark_type": "словесное",
        "owner": 'ООО "СмартТех"',
        "classes": [9, 42, 35],
        "status": "registered",
        "filing_date": "2016-09-14",
        "registration_date": "2017-11-28",
        "image_url": None,
    },
    # ── Combinative & Logo marks ────────────────────────────────────────────
    {
        "record_id": "RU0014001",
        "mark_text": "РОСАТОМ",
        "mark_type": "комбинированное",
        "owner": 'ГК "Росатом"',
        "classes": [4, 37, 40, 41, 42],
        "status": "registered",
        "filing_date": "2007-12-01",
        "registration_date": "2008-11-20",
        "image_url": "https://mock.fips.ru/img/rosatom.png",
    },
    {
        "record_id": "RU0014002",
        "mark_text": "РОСНЕФТЬ",
        "mark_type": "комбинированное",
        "owner": 'ПАО "НК «Роснефть»"',
        "classes": [4, 35, 37],
        "status": "registered",
        "filing_date": "1995-08-28",
        "registration_date": "1997-02-11",
        "image_url": "https://mock.fips.ru/img/rosneft.png",
    },
    {
        "record_id": "RU0014003",
        "mark_text": "РОСТЕЛЕКОМ",
        "mark_type": "словесное",
        "owner": 'ПАО "Ростелеком"',
        "classes": [38, 35, 42],
        "status": "registered",
        "filing_date": "1997-04-21",
        "registration_date": "1998-09-03",
        "image_url": None,
    },
    {
        "record_id": "RU0014004",
        "mark_text": "АЭРОФЛОТ",
        "mark_type": "словесное",
        "owner": 'ПАО "Аэрофлот"',
        "classes": [39, 43, 41],
        "status": "registered",
        "filing_date": "1992-01-15",
        "registration_date": "1993-06-30",
        "image_url": None,
    },
    {
        "record_id": "RU0014005",
        "mark_text": "РЖД",
        "mark_type": "словесное",
        "owner": 'ОАО "Российские железные дороги"',
        "classes": [39, 37, 35],
        "status": "registered",
        "filing_date": "2003-10-01",
        "registration_date": "2004-11-08",
        "image_url": None,
    },
]

# Build quick lookup
_RECORD_INDEX: dict[str, dict] = {r["record_id"]: r for r in _DATASET}

# Status lifecycle stages for submitted applications
_STATUS_LIFECYCLE = [
    "intake_check",
    "formal_examination",
    "substantive_examination",
    "publication",
    "registered",
]


# ---------------------------------------------------------------------------
# Phonetic normalisation helpers (basic Russian rules)
# ---------------------------------------------------------------------------

_PHONETIC_MAP = str.maketrans(
    {
        "Ё": "Е",
        "Й": "И",
        "Ъ": "",
        "Ь": "",
        "В": "Ф",  # дезвонченье: В/Ф
        "З": "С",  # З/С
        "Д": "Т",  # Д/Т
        "Г": "К",  # Г/К
        "Б": "П",  # Б/П
        "Ж": "Ш",  # Ж/Ш
    }
)

# Transliteration dict (кириллица → латиница)
_TRANSLIT_DICT: dict[int, str] = {
    ord('А'): 'A', ord('Б'): 'B', ord('В'): 'V', ord('Г'): 'G',
    ord('Д'): 'D', ord('Е'): 'E', ord('Ё'): 'E', ord('Ж'): 'ZH',
    ord('З'): 'Z', ord('И'): 'I', ord('Й'): 'Y', ord('К'): 'K',
    ord('Л'): 'L', ord('М'): 'M', ord('Н'): 'N', ord('О'): 'O',
    ord('П'): 'P', ord('Р'): 'R', ord('С'): 'S', ord('Т'): 'T',
    ord('У'): 'U', ord('Ф'): 'F', ord('Х'): 'KH', ord('Ц'): 'TS',
    ord('Ч'): 'CH', ord('Ш'): 'SH', ord('Щ'): 'SCH', ord('Ъ'): '',
    ord('Ы'): 'Y', ord('Ь'): '', ord('Э'): 'E', ord('Ю'): 'YU',
    ord('Я'): 'YA',
}


def _normalize_text(text: str) -> str:
    return re.sub(r"\s+", " ", text.upper().strip())


def _phonetic_key(text: str) -> str:
    """Produce a phonetically normalised key."""
    t = _normalize_text(text).translate(_PHONETIC_MAP)
    # Reduce consecutive duplicate consonants
    t = re.sub(r"(.)\1+", r"\1", t)
    return t


def _transliterate(text: str) -> str:
    upper = _normalize_text(text)
    result = []
    for ch in upper:
        mapped = _TRANSLIT_DICT.get(ord(ch))
        if mapped is not None:
            result.append(mapped)
        else:
            result.append(ch)
    return "".join(result)


def _bigram_similarity(a: str, b: str) -> float:
    """Dice coefficient on bigrams."""
    a_clean = re.sub(r"\s+", "", a.upper())
    b_clean = re.sub(r"\s+", "", b.upper())

    if not a_clean or not b_clean:
        return 0.0

    a_bigrams = [a_clean[i: i + 2] for i in range(len(a_clean) - 1)]
    b_bigrams = [b_clean[i: i + 2] for i in range(len(b_clean) - 1)]

    if not a_bigrams or not b_bigrams:
        # Single-char: direct match
        return 1.0 if a_clean == b_clean else 0.0

    a_set = set(a_bigrams)
    b_set = set(b_bigrams)
    intersection = a_set & b_set
    return 2 * len(intersection) / (len(a_set) + len(b_set))


def _contains_similarity(query: str, candidate: str) -> float:
    """Check if query is contained in candidate or vice versa (partial match)."""
    q = re.sub(r"\s+", "", query.upper())
    c = re.sub(r"\s+", "", candidate.upper())
    if q in c or c in q:
        return 0.85
    return 0.0


def _score_record(record: dict, query: SearchQuery) -> float:
    """
    Return a similarity score [0,1] for a registry record against the query.
    The score depends on query.search_type.
    """
    qt = _normalize_text(query.mark_text)
    rt = _normalize_text(record["mark_text"])

    if query.search_type == "exact":
        return 1.0 if qt == rt else 0.0

    if query.search_type == "fuzzy":
        bigram = _bigram_similarity(qt, rt)
        containment = _contains_similarity(qt, rt)
        return max(bigram, containment)

    if query.search_type == "phonetic":
        return _bigram_similarity(_phonetic_key(qt), _phonetic_key(rt))

    if query.search_type == "transliteration":
        # Check both directions
        qt_latin = _transliterate(qt)
        rt_latin = _transliterate(rt)
        score_direct = _bigram_similarity(qt, rt)
        score_translit = _bigram_similarity(qt_latin, rt_latin)
        score_cross1 = _bigram_similarity(qt_latin, rt)
        score_cross2 = _bigram_similarity(qt, rt_latin)
        return max(score_direct, score_translit, score_cross1, score_cross2)

    if query.search_type == "semantic":
        # Simple bigram; in production would use embeddings
        return _bigram_similarity(qt, rt)

    return 0.0


def _filter_by_classes(record: dict, classes: list[int] | None) -> bool:
    if not classes:
        return True
    return bool(set(record["classes"]) & set(classes))


def _to_record(data: dict) -> RegistryRecord:
    return RegistryRecord(**data)


# ---------------------------------------------------------------------------
# Fake status lifecycle (deterministic progression based on submission id)
# ---------------------------------------------------------------------------

_SUBMISSION_STORE: dict[str, dict[str, Any]] = {}


def _lifecycle_status(external_id: str) -> tuple[str, dict | None]:
    """
    Simulate a deterministic lifecycle using the submission timestamp embedded
    in external_id (or current time if not found).
    """
    record = _SUBMISSION_STORE.get(external_id)
    if not record:
        return "unknown", {"error": "Submission not found"}

    submitted_at: datetime = record["submitted_at"]
    elapsed = datetime.utcnow() - submitted_at
    days = elapsed.total_seconds() / 86400

    if days < 0.02:  # < ~30 min
        return "intake_check", {"message": "Проверка формальных требований"}
    elif days < 0.1:
        return "formal_examination", {"message": "Формальная экспертиза начата"}
    elif days < 1.0:
        return "substantive_examination", {
            "message": "Экспертиза по существу",
            "examiner": "Иванова А.П.",
        }
    elif days < 2.0:
        return "publication", {
            "message": "Заявка опубликована для оппозиционного периода",
            "bulletin_number": f"2024/{hashlib.md5(external_id.encode()).hexdigest()[:4]}",
        }
    else:
        return "registered", {
            "message": "Товарный знак зарегистрирован",
            "certificate_number": f"RU{int(hashlib.md5(external_id.encode()).hexdigest()[:8], 16) % 9000000 + 1000000}",
        }


# ---------------------------------------------------------------------------
# Provider class
# ---------------------------------------------------------------------------

_SIMILARITY_THRESHOLD = 0.35  # minimum score to include in results


class MockFipsProvider:
    """
    Mock implementation of TrademarkRegistryProvider protocol.
    Uses an in-memory dataset with similarity scoring.
    """

    async def search_marks(self, query: SearchQuery) -> list[RegistryRecord]:
        """Search registered trademarks (status=registered)."""
        return self._search(query, status_filter={"registered"})

    async def search_applications(self, query: SearchQuery) -> list[RegistryRecord]:
        """Search all applications including pending ones."""
        return self._search(query, status_filter={"registered", "pending"})

    def _search(
        self, query: SearchQuery, status_filter: set[str]
    ) -> list[RegistryRecord]:
        results = []
        for record in _DATASET:
            if record["status"] not in status_filter:
                continue
            if not _filter_by_classes(record, query.classes):
                continue
            if query.mark_type and record["mark_type"] != query.mark_type:
                continue

            score = _score_record(record, query)
            if score >= _SIMILARITY_THRESHOLD:
                results.append((score, record))

        # Sort by score descending, then alphabetically for stability
        results.sort(key=lambda x: (-x[0], x[1]["mark_text"]))
        top = results[: query.max_results]
        return [_to_record(r) for _, r in top]

    async def get_record(self, record_id: str) -> RegistryRecord | None:
        data = _RECORD_INDEX.get(record_id)
        return _to_record(data) if data else None

    async def submit_application(
        self, payload: SubmissionPayload
    ) -> SubmissionResult:
        external_id = f"FIPS-{uuid.uuid4().hex[:12].upper()}"
        _SUBMISSION_STORE[external_id] = {
            "payload": payload.model_dump(),
            "submitted_at": datetime.utcnow(),
        }
        return SubmissionResult(
            success=True,
            external_id=external_id,
            error_message=None,
        )

    async def get_status(self, external_submission_id: str) -> ExternalStatusResult:
        status, details = _lifecycle_status(external_submission_id)
        return ExternalStatusResult(
            external_id=external_submission_id,
            status=status,
            updated_at=datetime.utcnow().isoformat(),
            details=details,
        )
