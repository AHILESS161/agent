"""
KnowledgeLoader — scans the backend/knowledge/ directory and ingests all
supported files into the KnowledgePipeline.

Supported formats:
    .md   — Markdown (stripped to plain text before chunking)
    .txt  — Plain text

Metadata extraction:
    - title: first H1 heading in Markdown, or filename
    - source_type: derived from filename prefix conventions (see SOURCE_TYPE_MAP)
    - date: file modification time (ISO 8601)
    - format: "markdown" | "text"

Usage::

    from app.infrastructure.rag.knowledge_loader import KnowledgeLoader
    from app.infrastructure.rag.pipeline import get_pipeline

    loader = KnowledgeLoader(get_pipeline())
    loaded = loader.load_all()
    print(f"Loaded {loaded} source files")

To load a specific file::

    source_id = loader.load_file(Path("knowledge/gk_rf_part4_trademarks.md"))
"""

from __future__ import annotations

import logging
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from app.infrastructure.rag.pipeline import KnowledgePipeline, get_pipeline

logger = logging.getLogger(__name__)

# Default knowledge directory relative to the backend root
_DEFAULT_KNOWLEDGE_DIR = Path(__file__).resolve().parents[4] / "knowledge"

# Map filename stem prefixes to semantic source_type tags
SOURCE_TYPE_MAP: dict[str, str] = {
    "gk_rf": "regulation",
    "rospatent": "guideline",
    "nice": "classification",
    "faq": "faq",
    "manual": "manual",
    "template": "template",
}

SUPPORTED_EXTENSIONS = {".md", ".txt"}


class KnowledgeLoader:
    """
    Scans a knowledge directory and ingests supported documents into a
    KnowledgePipeline.

    Args:
        pipeline: Target pipeline to ingest into.
                  Defaults to the application-level singleton.
        knowledge_dir: Path to the directory containing knowledge files.
                       Defaults to backend/knowledge/.
    """

    def __init__(
        self,
        pipeline: Optional[KnowledgePipeline] = None,
        knowledge_dir: Optional[Path] = None,
    ) -> None:
        self.pipeline = pipeline or get_pipeline()
        self.knowledge_dir = knowledge_dir or _DEFAULT_KNOWLEDGE_DIR

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def load_all(self, recursive: bool = False) -> int:
        """
        Ingest all supported files in the knowledge directory.

        Args:
            recursive: If True, also scan subdirectories.

        Returns:
            Number of files successfully loaded.
        """
        if not self.knowledge_dir.exists():
            logger.warning(
                f"KnowledgeLoader: knowledge dir not found — {self.knowledge_dir}"
            )
            return 0

        pattern = "**/*" if recursive else "*"
        files = [
            p for p in self.knowledge_dir.glob(pattern)
            if p.is_file() and p.suffix.lower() in SUPPORTED_EXTENSIONS
        ]

        if not files:
            logger.info(f"KnowledgeLoader: no supported files in {self.knowledge_dir}")
            return 0

        loaded = 0
        for path in sorted(files):
            try:
                source_id = self.load_file(path)
                if source_id:
                    loaded += 1
            except Exception as exc:
                logger.error(f"KnowledgeLoader: failed to load {path}: {exc}")

        logger.info(
            f"KnowledgeLoader: loaded {loaded}/{len(files)} files from "
            f"{self.knowledge_dir}"
        )
        return loaded

    def load_file(self, path: Path) -> str:
        """
        Ingest a single file into the pipeline.

        Args:
            path: Absolute or relative path to the file.

        Returns:
            source_id assigned by the pipeline, or "" on failure.
        """
        path = Path(path).resolve()
        if not path.exists():
            logger.warning(f"KnowledgeLoader: file not found — {path}")
            return ""

        ext = path.suffix.lower()
        if ext not in SUPPORTED_EXTENSIONS:
            logger.debug(f"KnowledgeLoader: unsupported extension {ext} — {path}")
            return ""

        raw_text = path.read_text(encoding="utf-8")
        metadata = self._extract_metadata(path, raw_text)

        # Strip Markdown syntax to improve tokenisation quality
        text = _strip_markdown(raw_text) if ext == ".md" else raw_text

        source_id = self.pipeline.ingest(
            source_path=str(path),
            source_type=metadata["source_type"],
            metadata=metadata,
        )
        logger.info(
            f"KnowledgeLoader: ingested {path.name!r} → "
            f"source_id={source_id!r}, chunks={self.pipeline.total_chunks}"
        )
        return source_id

    # ------------------------------------------------------------------
    # Metadata extraction
    # ------------------------------------------------------------------

    def _extract_metadata(self, path: Path, raw_text: str) -> dict:
        """Build a metadata dict from the file path and content."""
        stem = path.stem.lower()
        ext = path.suffix.lower()

        # Determine source_type from filename prefix
        source_type = "document"
        for prefix, stype in SOURCE_TYPE_MAP.items():
            if stem.startswith(prefix):
                source_type = stype
                break

        # Extract title
        title = _extract_title_from_markdown(raw_text) if ext == ".md" else None
        if not title:
            title = path.stem.replace("_", " ").title()

        # File modification date
        mtime = datetime.fromtimestamp(path.stat().st_mtime, tz=timezone.utc)

        return {
            "title": title,
            "source_type": source_type,
            "date": mtime.date().isoformat(),
            "format": "markdown" if ext == ".md" else "text",
            "filename": path.name,
        }


# ---------------------------------------------------------------------------
# Markdown helpers
# ---------------------------------------------------------------------------

_HEADING_RE = re.compile(r"^#{1,6}\s+(.+)$", re.MULTILINE)
_CODE_BLOCK_RE = re.compile(r"```.*?```", re.DOTALL)
_INLINE_CODE_RE = re.compile(r"`[^`]+`")
_BOLD_ITALIC_RE = re.compile(r"\*{1,3}([^*]+)\*{1,3}")
_LINK_RE = re.compile(r"\[([^\]]+)\]\([^)]+\)")
_IMAGE_RE = re.compile(r"!\[[^\]]*\]\([^)]+\)")
_HTML_TAG_RE = re.compile(r"<[^>]+>")
_HORIZONTAL_RULE_RE = re.compile(r"^[-*_]{3,}$", re.MULTILINE)
_TABLE_SEPARATOR_RE = re.compile(r"^\|[-| :]+\|$", re.MULTILINE)


def _extract_title_from_markdown(text: str) -> Optional[str]:
    """Return the first H1 heading found in the Markdown text."""
    match = re.search(r"^#\s+(.+)$", text, re.MULTILINE)
    return match.group(1).strip() if match else None


def _strip_markdown(text: str) -> str:
    """
    Convert Markdown to plain text for tokenisation.
    Preserves most textual content while removing syntax noise.
    """
    # Remove fenced code blocks
    text = _CODE_BLOCK_RE.sub(" ", text)
    # Remove images
    text = _IMAGE_RE.sub(" ", text)
    # Convert links to their visible text
    text = _LINK_RE.sub(r"\1", text)
    # Remove bold/italic markers
    text = _BOLD_ITALIC_RE.sub(r"\1", text)
    # Remove inline code
    text = _INLINE_CODE_RE.sub(" ", text)
    # Remove HTML tags
    text = _HTML_TAG_RE.sub(" ", text)
    # Remove horizontal rules and table separators
    text = _HORIZONTAL_RULE_RE.sub(" ", text)
    text = _TABLE_SEPARATOR_RE.sub(" ", text)
    # Convert headings to plain text (keep the heading text)
    text = _HEADING_RE.sub(r"\1", text)
    # Collapse pipe characters from tables
    text = text.replace("|", " ")
    # Collapse extra whitespace
    text = re.sub(r" {2,}", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()
