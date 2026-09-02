"""
FR-019 / SC-008 as an executable assertion rather than a promise (T075).

Phase 4a defines, validates, versions and serves prompt templates. It never
executes one. That boundary is the whole reason 4a and 4b are separate specs,
and it is easy to erode by accident -- a "quick test against the real model"
in a test file would do it.

So: no module under apps/prompts/ may import an HTTP client or a model SDK.
This is checked by reading the source, not by monkeypatching a client, because
the point is that the import does not exist at all.
"""
import pathlib

import apps.prompts

# Anything that could reach a model. `requests`/`httpx` are the generic HTTP
# clients; the rest are the SDKs a future 4b might legitimately use -- in
# apps/llm, not here.
_FORBIDDEN_IMPORTS = (
    "requests",
    "httpx",
    "aiohttp",
    "urllib.request",
    "ollama",
    "openai",
    "anthropic",
    "langchain",
    "llama_index",
)

_PACKAGE_ROOT = pathlib.Path(apps.prompts.__file__).parent


def _source_files():
    return sorted(_PACKAGE_ROOT.rglob("*.py"))


def test_there_are_source_files_to_check():
    """
    Guards the two tests below from passing vacuously if the glob ever stops
    matching -- the same failure mode T010 exists to prevent for the
    whitelist.
    """
    files = _source_files()
    assert len(files) >= 8
    names = {f.name for f in files}
    assert {"library.py", "bindings.py", "validation.py", "views.py"} <= names


def test_no_module_imports_an_llm_client():
    """FR-019. No module under apps/prompts/ can reach a model."""
    offenders = []
    for path in _source_files():
        source = path.read_text()
        for line in source.splitlines():
            stripped = line.strip()
            if not (
                stripped.startswith("import ") or stripped.startswith("from ")
            ):
                continue
            for forbidden in _FORBIDDEN_IMPORTS:
                if stripped.startswith(
                    f"import {forbidden}"
                ) or stripped.startswith(f"from {forbidden}"):
                    offenders.append(f"{path.name}: {stripped}")

    assert not offenders, (
        "Phase 4a must make no language-model call (FR-019/SC-008). "
        f"Found: {offenders}. Generation belongs to Phase 4b."
    )


def test_no_module_mentions_a_model_endpoint():
    """
    Belt and braces: an inlined URL would reach a model without importing a
    named client. Docstrings and comments are excluded -- this module and
    library.py both discuss ollama models by name, legitimately.
    """
    offenders = []
    for path in _source_files():
        if path.name == "test_no_llm.py":
            continue
        for line in path.read_text().splitlines():
            stripped = line.strip()
            if stripped.startswith("#") or '"""' in stripped:
                continue
            if "11434" in stripped or "/api/generate" in stripped:
                offenders.append(f"{path.name}: {stripped}")

    assert not offenders, f"model endpoint referenced in Phase 4a: {offenders}"
