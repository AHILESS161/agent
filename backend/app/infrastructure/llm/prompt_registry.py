"""
Prompt Registry — loads, stores, and renders YAML-defined prompt definitions.

YAML file structure expected:
    id: string
    version: string          # e.g. "1.0.0"
    description: string
    system: string
    user_template: string    # Jinja2 template
    input_schema: object     # JSON Schema
    output_schema: object    # JSON Schema
    examples: list
    guardrails: list[string]
    evaluation_notes: string
"""
from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml
from jinja2 import Environment, StrictUndefined, TemplateError, UndefinedError

logger = logging.getLogger(__name__)


@dataclass
class PromptDefinition:
    id: str
    version: str
    description: str
    system: str
    user_template: str
    input_schema: dict = field(default_factory=dict)
    output_schema: dict = field(default_factory=dict)
    examples: list[dict] = field(default_factory=list)
    guardrails: list[str] = field(default_factory=list)
    evaluation_notes: str = ""

    @classmethod
    def from_dict(cls, data: dict) -> "PromptDefinition":
        return cls(
            id=data["id"],
            version=data["version"],
            description=data.get("description", ""),
            system=data["system"],
            user_template=data["user_template"],
            input_schema=data.get("input_schema", {}),
            output_schema=data.get("output_schema", {}),
            examples=data.get("examples", []),
            guardrails=data.get("guardrails", []),
            evaluation_notes=data.get("evaluation_notes", ""),
        )


def _version_tuple(v: str) -> tuple[int, ...]:
    """Convert version string like '1.2.3' to a comparable tuple."""
    try:
        return tuple(int(x) for x in v.split("."))
    except ValueError:
        return (0,)


class PromptRegistry:
    """
    Central registry for all prompt definitions.

    Usage:
        registry = PromptRegistry()
        registry.load_from_directory("prompts/")
        rendered = registry.render("intake.missing_info", {"fields": [...]})
    """

    def __init__(self) -> None:
        # {prompt_id: {version_str: PromptDefinition}}
        self._store: dict[str, dict[str, PromptDefinition]] = {}
        self._jinja_env = Environment(undefined=StrictUndefined, autoescape=False)

    # ------------------------------------------------------------------
    # Loading
    # ------------------------------------------------------------------

    def load_from_directory(self, path: str | Path) -> int:
        """Recursively load all YAML files from the given directory.

        Returns the number of prompt files successfully loaded.
        Returns 0 if the directory does not exist (non-fatal — useful for tests).
        """
        root = Path(path)
        if not root.exists():
            logger.warning("Prompts directory not found: %s (returning 0)", root)
            return 0

        loaded = 0
        for yaml_file in sorted(root.rglob("*.yaml")):
            try:
                self._load_file(yaml_file)
                loaded += 1
            except Exception as exc:
                logger.warning("Failed to load prompt file %s: %s", yaml_file, exc)

        logger.info("PromptRegistry: loaded %d prompt(s) from %s", loaded, root)
        return loaded

    def _load_file(self, path: Path) -> None:
        with open(path, encoding="utf-8") as fh:
            data = yaml.safe_load(fh)

        if not isinstance(data, dict):
            raise ValueError(f"Expected a YAML mapping, got {type(data)}")

        prompt = PromptDefinition.from_dict(data)
        if prompt.id not in self._store:
            self._store[prompt.id] = {}
        self._store[prompt.id][prompt.version] = prompt
        logger.debug("Loaded prompt '%s' v%s", prompt.id, prompt.version)

    # ------------------------------------------------------------------
    # Retrieval
    # ------------------------------------------------------------------

    def get(self, prompt_id: str, version: str | None = None) -> PromptDefinition | None:
        """Return a specific version or the latest version of a prompt.

        Returns None if the prompt id (or requested version) is not found.
        """
        if prompt_id not in self._store:
            return None

        versions = self._store[prompt_id]

        if version is not None:
            if version not in versions:
                return None
            return versions[version]

        # Return latest by semantic version ordering
        latest_ver = max(versions.keys(), key=_version_tuple)
        return versions[latest_ver]

    def list_versions(self, prompt_id: str) -> list[str]:
        """Return all loaded version strings for the given prompt id."""
        if prompt_id not in self._store:
            return []
        return sorted(self._store[prompt_id].keys(), key=_version_tuple)

    def list_ids(self) -> list[str]:
        """Return all loaded prompt ids (sorted)."""
        return sorted(self._store.keys())

    def list_all(self) -> list[dict[str, Any]]:
        """Return a summary list of all registered prompts (sorted by id+version)."""
        result = []
        for prompt_id, versions in self._store.items():
            for ver, defn in versions.items():
                result.append(
                    {
                        "id": prompt_id,
                        "version": ver,
                        "description": defn.description,
                    }
                )
        return sorted(result, key=lambda x: (x["id"], x["version"]))

    # ------------------------------------------------------------------
    # Rendering
    # ------------------------------------------------------------------

    def render(self, prompt_id: str, variables: dict, version: str | None = None) -> str:
        """
        Render the user_template of a prompt with Jinja2.

        Returns the rendered string (to be used as the user message content).
        Raises:
            KeyError — if the prompt id or version is not found.
            ValueError — on template errors or missing variables.
        """
        defn = self.get(prompt_id, version)
        if defn is None:
            raise KeyError(f"Prompt '{prompt_id}' (version={version}) not found in registry")
        try:
            template = self._jinja_env.from_string(defn.user_template)
            return template.render(**variables)
        except UndefinedError as exc:
            raise ValueError(
                f"Missing template variable in prompt '{prompt_id}': {exc}"
            ) from exc
        except TemplateError as exc:
            raise ValueError(
                f"Template error in prompt '{prompt_id}': {exc}"
            ) from exc

    # ------------------------------------------------------------------
    # Validation
    # ------------------------------------------------------------------

    def validate_input(self, prompt_id: str, input_data: dict) -> list[str]:
        """
        Validate input_data against the prompt's input_schema.
        Returns a list of validation error messages (empty = valid).

        Raises:
            KeyError — if the prompt id is not registered.

        Uses jsonschema if available; otherwise does a best-effort key check.
        """
        defn = self.get(prompt_id)
        if defn is None:
            raise KeyError(f"Prompt '{prompt_id}' not found in registry")
        schema = defn.input_schema
        if not schema:
            return []

        try:
            import jsonschema  # type: ignore

            validator = jsonschema.Draft7Validator(schema)
            errors = [e.message for e in validator.iter_errors(input_data)]
            if errors:
                raise ValueError(
                    f"Input validation failed for prompt '{prompt_id}': {errors}"
                )
            return errors
        except ImportError:
            # Fallback: check required fields manually
            required = schema.get("required", [])
            missing = [f for f in required if f not in input_data]
            if missing:
                raise ValueError(
                    f"Input validation failed for prompt '{prompt_id}': "
                    f"Missing required fields: {missing}"
                )
            return []

    # ------------------------------------------------------------------
    # Convenience: build full LLMMessage list from a prompt + variables
    # ------------------------------------------------------------------

    def build_messages(
        self, prompt_id: str, variables: dict, version: str | None = None
    ) -> list[dict[str, str]]:
        """
        Returns a list of chat messages ready for the LLM provider:
            [{"role": "system", "content": "..."}, {"role": "user", "content": "..."}]
        """
        defn = self.get(prompt_id, version)
        if defn is None:
            raise KeyError(f"Prompt '{prompt_id}' (version={version}) not found in registry")
        rendered_user = self.render(prompt_id, variables, version)
        return [
            {"role": "system", "content": defn.system},
            {"role": "user", "content": rendered_user},
        ]
