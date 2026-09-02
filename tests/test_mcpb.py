import json
import zipfile
from importlib.metadata import PackageNotFoundError, version

from context_note.mcpb import build_mcpb


def test_build_mcpb_produces_valid_zip_with_manifest_and_placeholder(tmp_path):
    out = tmp_path / "context-note.mcpb"
    result = build_mcpb(out, python="/fake/venv/bin/python")

    assert result == out
    assert out.exists()

    with zipfile.ZipFile(out) as zf:
        assert set(zf.namelist()) == {"manifest.json", "server/main.py"}
        manifest = json.loads(zf.read("manifest.json"))

    assert manifest["manifest_version"] == "0.3"
    assert manifest["name"] == "context-note"
    assert manifest["server"]["type"] == "python"
    assert manifest["server"]["entry_point"] == "server/main.py"
    assert manifest["server"]["mcp_config"]["command"] == "/fake/venv/bin/python"
    assert manifest["server"]["mcp_config"]["args"] == ["-m", "context_note.server"]


def test_build_mcpb_declares_prompts(tmp_path):
    # Claude Desktop lists an undeclared prompt fine but refuses to call it
    # ("attempted undeclared prompt") unless it's also in manifest.json, and
    # requires each declared prompt to have "text" ("Invalid manifest:
    # prompts: Required" otherwise) -- this is a separate, static-templating
    # mechanism from MCP's own dynamic prompts/get.
    out = tmp_path / "context-note.mcpb"
    build_mcpb(out, python="/fake/python")

    with zipfile.ZipFile(out) as zf:
        manifest = json.loads(zf.read("manifest.json"))

    prompts = {p["name"]: p for p in manifest["prompts"]}
    assert "da Cross Context" in prompts
    prompt = prompts["da Cross Context"]
    assert prompt["arguments"] == ["query"]
    assert "${arguments.query}" in prompt["text"]


def test_build_mcpb_defaults_command_to_current_interpreter(tmp_path):
    import sys

    out = tmp_path / "context-note.mcpb"
    build_mcpb(out)

    with zipfile.ZipFile(out) as zf:
        manifest = json.loads(zf.read("manifest.json"))
    assert manifest["server"]["mcp_config"]["command"] == sys.executable


def test_build_mcpb_creates_parent_directories(tmp_path):
    out = tmp_path / "nested" / "dir" / "context-note.mcpb"
    result = build_mcpb(out, python="/fake/python")
    assert result.exists()


def test_build_mcpb_version_matches_installed_package(tmp_path):
    # Regression test: the manifest's version used to be a separate literal
    # ("0.1.0") hand-duplicated from pyproject.toml, so a version bump there
    # wouldn't reach the built bundle unless someone remembered to update
    # this file too.
    out = tmp_path / "context-note.mcpb"
    build_mcpb(out, python="/fake/python")

    with zipfile.ZipFile(out) as zf:
        manifest = json.loads(zf.read("manifest.json"))

    try:
        expected = version("context-note")
    except PackageNotFoundError:
        expected = "0.0.0"
    assert manifest["version"] == expected
