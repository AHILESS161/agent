"""Internal stdin/stdout parser protocol. Never logs uploaded data."""
from __future__ import annotations

import json
import os
import sys
from dataclasses import asdict


def main():
    if os.name != "nt":
        import resource
        memory = int(os.environ.get("DOCUMENT_PARSE_MEMORY_MB", "768")) * 1024 * 1024
        cpu = int(os.environ.get("DOCUMENT_PARSE_TIMEOUT", "120"))
        resource.setrlimit(resource.RLIMIT_AS, (memory, memory))
        resource.setrlimit(resource.RLIMIT_CPU, (cpu, cpu))
    from app.core.config import settings
    from app.services.document_text_extractor import extract_pages_from_bytes
    from app.services.file_storage import validate_upload
    from app.services.mark_image import process_mark_image

    try:
        content = sys.stdin.buffer.read(settings.MAX_UPLOAD_MB * 1024 * 1024 + 1)
        filename = sys.argv[2]
        validate_upload(content, filename)
        if sys.argv[1] == "image":
            result = asdict(process_mark_image(content, filename))
        else:
            pages = extract_pages_from_bytes(content, filename)
            if sum(len(p.text) for p in pages) > 1_000_000:
                raise ValueError("Извлечённый текст превышает лимит")
            result = [asdict(page) for page in pages]
        response = {"result": result}
    except Exception:
        response = {"error": "Не удалось разобрать документ в пределах лимитов сервера"}
    sys.stdout.buffer.write(json.dumps(response, ensure_ascii=True).encode("ascii"))


if __name__ == "__main__":
    main()
