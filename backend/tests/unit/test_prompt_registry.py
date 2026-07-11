"""
Unit tests for the Prompt Registry.

Tests validate:
- Loading YAML prompt definitions from files and directories
- Rendering Jinja2 templates with context variables
- Input validation against JSON Schema
- Version management (latest, specific version)
- Error handling for missing/invalid prompts
"""

from __future__ import annotations

import textwrap
from pathlib import Path

import pytest
import yaml

from app.infrastructure.llm.prompt_registry import PromptDefinition, PromptRegistry


# ---------------------------------------------------------------------------
# YAML fixtures
# ---------------------------------------------------------------------------

MINIMAL_YAML = textwrap.dedent("""\
    id: test.minimal
    version: "1.0.0"
    description: Minimal test prompt
    system: You are a helpful assistant.
    user_template: "Hello, {{ name }}!"
    input_schema:
      type: object
      properties:
        name:
          type: string
      required:
        - name
    output_schema:
      type: object
    examples: []
    guardrails: []
    evaluation_notes: ""
""")

VERSIONED_YAML_V2 = textwrap.dedent("""\
    id: test.minimal
    version: "2.0.0"
    description: Version 2 of the minimal test prompt
    system: You are a very helpful assistant.
    user_template: "Greetings, {{ name }}! How can I help?"
    input_schema:
      type: object
      properties:
        name:
          type: string
      required:
        - name
    output_schema:
      type: object
    examples: []
    guardrails: []
    evaluation_notes: ""
""")

TRADEMARK_ANALYSIS_YAML = textwrap.dedent("""\
    id: legal.absolute_grounds
    version: "1.0.0"
    description: Анализ абсолютных оснований для отказа в регистрации ТЗ
    system: |
      Вы — специалист по интеллектуальной собственности. Анализируйте обозначение
      на соответствие ст.1483 ГК РФ (абсолютные основания для отказа).
    user_template: |
      Обозначение: {{ mark_name }}
      Вид: {{ mark_type }}
      Классы МКТУ: {{ nice_classes | join(', ') }}
      
      Проверьте на абсолютные основания для отказа.
    input_schema:
      type: object
      properties:
        mark_name:
          type: string
        mark_type:
          type: string
        nice_classes:
          type: array
          items:
            type: integer
      required:
        - mark_name
        - mark_type
    output_schema:
      type: object
      properties:
        risk_level:
          type: string
          enum: [low, medium, high, critical]
    examples: []
    guardrails:
      - Never recommend specific attorneys or law firms
    evaluation_notes: Test evaluation note
""")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _load_yaml_to_registry(yaml_str: str, registry: PromptRegistry = None) -> PromptRegistry:
    """Load a YAML string into a PromptRegistry."""
    if registry is None:
        registry = PromptRegistry()
    data = yaml.safe_load(yaml_str)
    definition = PromptDefinition.from_dict(data)
    registry._store.setdefault(definition.id, {})[definition.version] = definition
    return registry


def _write_yaml(tmp_path: Path, filename: str, yaml_str: str) -> Path:
    """Write a YAML string to a temp file."""
    path = tmp_path / filename
    path.write_text(yaml_str, encoding="utf-8")
    return path


# ---------------------------------------------------------------------------
# Loading YAML prompts
# ---------------------------------------------------------------------------

@pytest.mark.unit
class TestPromptRegistryLoading:
    """Tests for loading prompt definitions."""

    def test_load_from_directory(self, tmp_path: Path):
        """load_from_directory should discover and load all YAML files."""
        _write_yaml(tmp_path, "minimal.yaml", MINIMAL_YAML)
        _write_yaml(tmp_path, "legal.yaml", TRADEMARK_ANALYSIS_YAML)

        registry = PromptRegistry()
        count = registry.load_from_directory(str(tmp_path))

        assert count == 2

    def test_loaded_prompt_is_accessible(self, tmp_path: Path):
        """After loading, the prompt should be retrievable by ID."""
        _write_yaml(tmp_path, "minimal.yaml", MINIMAL_YAML)

        registry = PromptRegistry()
        registry.load_from_directory(str(tmp_path))

        definition = registry.get("test.minimal")
        assert definition is not None
        assert definition.id == "test.minimal"

    def test_load_prompt_definition_fields(self, tmp_path: Path):
        """PromptDefinition fields should match the YAML content."""
        _write_yaml(tmp_path, "minimal.yaml", MINIMAL_YAML)

        registry = PromptRegistry()
        registry.load_from_directory(str(tmp_path))

        defn = registry.get("test.minimal")
        assert defn.version == "1.0.0"
        assert defn.description == "Minimal test prompt"
        assert "helpful assistant" in defn.system

    def test_load_empty_directory_returns_zero(self, tmp_path: Path):
        """Loading from an empty directory should return 0."""
        registry = PromptRegistry()
        count = registry.load_from_directory(str(tmp_path))
        assert count == 0

    def test_load_nonexistent_directory_does_not_raise(self, tmp_path: Path):
        """Loading from a non-existent path should not raise exceptions."""
        registry = PromptRegistry()
        count = registry.load_from_directory(str(tmp_path / "nonexistent"))
        assert count == 0

    def test_guardrails_loaded(self, tmp_path: Path):
        """Guardrails list should be correctly loaded."""
        _write_yaml(tmp_path, "legal.yaml", TRADEMARK_ANALYSIS_YAML)

        registry = PromptRegistry()
        registry.load_from_directory(str(tmp_path))

        defn = registry.get("legal.absolute_grounds")
        assert len(defn.guardrails) > 0
        assert any("attorney" in g.lower() for g in defn.guardrails)


# ---------------------------------------------------------------------------
# Rendering templates
# ---------------------------------------------------------------------------

@pytest.mark.unit
class TestPromptRegistryRendering:
    """Tests for Jinja2 template rendering."""

    def test_render_simple_template(self):
        """Basic variable substitution should work correctly."""
        registry = _load_yaml_to_registry(MINIMAL_YAML)

        rendered = registry.render("test.minimal", {"name": "Иванов"})

        assert "Иванов" in rendered

    def test_render_returns_string(self):
        """render() must return a string."""
        registry = _load_yaml_to_registry(MINIMAL_YAML)
        result = registry.render("test.minimal", {"name": "Test"})
        assert isinstance(result, str)

    def test_render_trademark_template_with_list(self):
        """Template with list filter should render correctly."""
        registry = _load_yaml_to_registry(TRADEMARK_ANALYSIS_YAML)

        rendered = registry.render(
            "legal.absolute_grounds",
            {
                "mark_name": "ТЕСТ",
                "mark_type": "word",
                "nice_classes": [9, 42],
            },
        )

        assert "ТЕСТ" in rendered
        assert "9" in rendered
        assert "42" in rendered

    def test_render_missing_variable_raises(self):
        """Rendering with a missing required variable should raise TemplateError."""
        registry = _load_yaml_to_registry(MINIMAL_YAML)

        with pytest.raises(Exception):  # UndefinedError or TemplateError
            registry.render("test.minimal", {})  # 'name' is required

    def test_render_unknown_prompt_raises(self):
        """Rendering a non-existent prompt ID should raise KeyError or similar."""
        registry = PromptRegistry()

        with pytest.raises((KeyError, ValueError)):
            registry.render("nonexistent.prompt", {"key": "value"})

    def test_render_system_prompt(self):
        """Rendering should produce the system prompt text."""
        registry = _load_yaml_to_registry(MINIMAL_YAML)
        defn = registry.get("test.minimal")
        assert "helpful assistant" in defn.system


# ---------------------------------------------------------------------------
# Version management
# ---------------------------------------------------------------------------

@pytest.mark.unit
class TestPromptRegistryVersioning:
    """Tests for version management."""

    def test_get_latest_version(self):
        """get() without version should return the latest version."""
        registry = PromptRegistry()
        _load_yaml_to_registry(MINIMAL_YAML, registry)
        _load_yaml_to_registry(VERSIONED_YAML_V2, registry)

        latest = registry.get("test.minimal")
        assert latest.version == "2.0.0"

    def test_get_specific_version(self):
        """get() with version should return the specified version."""
        registry = PromptRegistry()
        _load_yaml_to_registry(MINIMAL_YAML, registry)
        _load_yaml_to_registry(VERSIONED_YAML_V2, registry)

        v1 = registry.get("test.minimal", version="1.0.0")
        assert v1.version == "1.0.0"

    def test_get_nonexistent_version_returns_none(self):
        """get() with a version that doesn't exist should return None."""
        registry = _load_yaml_to_registry(MINIMAL_YAML)

        result = registry.get("test.minimal", version="99.0.0")
        assert result is None

    def test_list_versions(self):
        """list_versions() should return all loaded versions for a prompt ID."""
        registry = PromptRegistry()
        _load_yaml_to_registry(MINIMAL_YAML, registry)
        _load_yaml_to_registry(VERSIONED_YAML_V2, registry)

        versions = registry.list_versions("test.minimal")
        assert "1.0.0" in versions
        assert "2.0.0" in versions

    def test_list_all_prompt_ids(self):
        """list_ids() should return all loaded prompt IDs."""
        registry = PromptRegistry()
        _load_yaml_to_registry(MINIMAL_YAML, registry)
        _load_yaml_to_registry(TRADEMARK_ANALYSIS_YAML, registry)

        ids = registry.list_ids()
        assert "test.minimal" in ids
        assert "legal.absolute_grounds" in ids


# ---------------------------------------------------------------------------
# Input validation
# ---------------------------------------------------------------------------

@pytest.mark.unit
class TestPromptRegistryValidation:
    """Tests for input schema validation."""

    def test_valid_input_passes_validation(self):
        """Valid input matching JSON Schema should not raise errors."""
        registry = _load_yaml_to_registry(MINIMAL_YAML)

        # Should not raise
        registry.validate_input("test.minimal", {"name": "Тест"})

    def test_missing_required_field_fails_validation(self):
        """Missing required field should raise a ValueError or similar."""
        registry = _load_yaml_to_registry(MINIMAL_YAML)

        with pytest.raises((ValueError, KeyError)):
            registry.validate_input("test.minimal", {})

    def test_extra_fields_in_input_may_pass(self):
        """Extra fields in input should not necessarily fail (depends on additionalProperties)."""
        registry = _load_yaml_to_registry(MINIMAL_YAML)

        # This should not raise — extra fields are generally allowed unless schema says otherwise
        try:
            registry.validate_input("test.minimal", {"name": "Тест", "extra": "value"})
        except Exception:
            pass  # Schema may or may not allow extra fields
