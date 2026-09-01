import json

from pathlib import Path

from context_note.config import Config
from context_note.ingest import file_hash
from context_note.store import Store
from context_note.watch import (
    conversations_url_from_manifest,
    handle_manifests,
    looks_like_export,
    looks_like_manifest,
)


def test_recognizes_conversations_json():
    assert looks_like_export(Path("conversations.json"))
    assert not looks_like_export(Path("other.json"))


def test_recognizes_classic_export_zip_names():
    assert looks_like_export(Path("claude-export.zip"))
    assert looks_like_export(Path("data-2026-08-31-12-00-00-batch-0000.zip"))
    assert looks_like_export(Path("my-export.zip"))


def test_recognizes_conversations_batch_zip():
    assert looks_like_export(Path("conversations-000.zip"))
    assert looks_like_export(Path("CONVERSATIONS-012.zip"))


def test_does_not_match_other_category_batches():
    # projects/users/memories zips carry no conversation content and aren't
    # ingestable by this tool -- only the conversations category matters.
    assert not looks_like_export(Path("projects-000.zip"))
    assert not looks_like_export(Path("light_metadata-000.zip"))
    assert not looks_like_export(Path("memories-000.zip"))


def test_rejects_unrelated_files():
    assert not looks_like_export(Path("resume.pdf"))
    assert not looks_like_export(Path("random.zip"))
    assert not looks_like_export(Path("manifest-abc123.json"))


def test_looks_like_manifest():
    assert looks_like_manifest(Path("manifest-5d78-e277-1788241479-2026-09-01.json"))
    assert looks_like_manifest(Path("MANIFEST-abc.json"))
    assert not looks_like_manifest(Path("conversations.json"))
    assert not looks_like_manifest(Path("manifest.zip"))


def write_manifest(path, entries):
    path.write_text(json.dumps({"data_files": entries}))


def test_conversations_url_from_manifest_finds_the_right_category(tmp_path):
    path = tmp_path / "manifest-abc.json"
    write_manifest(
        path,
        [
            {"category": "projects", "export_url": "https://example.com/projects"},
            {"category": "conversations", "export_url": "https://example.com/convos"},
        ],
    )
    assert conversations_url_from_manifest(path) == "https://example.com/convos"


def test_conversations_url_from_manifest_missing_category(tmp_path):
    path = tmp_path / "manifest-abc.json"
    write_manifest(path, [{"category": "projects", "export_url": "https://example.com/p"}])
    assert conversations_url_from_manifest(path) is None


def test_conversations_url_from_manifest_invalid_json(tmp_path):
    path = tmp_path / "manifest-abc.json"
    path.write_text("not json")
    assert conversations_url_from_manifest(path) is None


def test_handle_manifests_opens_conversations_url_once(tmp_path, monkeypatch):
    downloads = tmp_path / "Downloads"
    downloads.mkdir()
    write_manifest(
        downloads / "manifest-abc.json",
        [{"category": "conversations", "export_url": "https://example.com/convos"}],
    )

    opened_urls = []
    monkeypatch.setattr("context_note.watch.webbrowser.open", opened_urls.append)

    store = Store(tmp_path / "index.db")
    cfg = Config()
    seen: dict = {}

    # is_stable() needs the size to be seen unchanged across two polls after
    # the first sighting (three calls total) before treating it as ready.
    assert handle_manifests([downloads], store, cfg, seen) == []
    assert handle_manifests([downloads], store, cfg, seen) == []
    assert opened_urls == []

    opened = handle_manifests([downloads], store, cfg, seen)
    assert [p.name for p in opened] == ["manifest-abc.json"]
    assert opened_urls == ["https://example.com/convos"]

    # A later poll (e.g. after a service restart) must not reopen the
    # same one-time-use link.
    opened_again = handle_manifests([downloads], store, cfg, seen)
    assert opened_again == []
    assert opened_urls == ["https://example.com/convos"]


def test_handle_manifests_respects_config_toggle(tmp_path, monkeypatch):
    downloads = tmp_path / "Downloads"
    downloads.mkdir()
    write_manifest(
        downloads / "manifest-abc.json",
        [{"category": "conversations", "export_url": "https://example.com/convos"}],
    )

    opened_urls = []
    monkeypatch.setattr("context_note.watch.webbrowser.open", opened_urls.append)

    store = Store(tmp_path / "index.db")
    cfg = Config(auto_open_export_manifest=False)
    seen: dict = {}

    handle_manifests([downloads], store, cfg, seen)
    handle_manifests([downloads], store, cfg, seen)
    assert opened_urls == []


def test_handle_manifests_marks_unrecognized_manifest_handled(tmp_path, monkeypatch):
    # A manifest with no conversations entry shouldn't be re-inspected on
    # every poll forever.
    downloads = tmp_path / "Downloads"
    downloads.mkdir()
    write_manifest(downloads / "manifest-abc.json", [{"category": "projects"}])

    monkeypatch.setattr("context_note.watch.webbrowser.open", lambda url: None)

    store = Store(tmp_path / "index.db")
    cfg = Config()
    seen: dict = {}

    handle_manifests([downloads], store, cfg, seen)
    handle_manifests([downloads], store, cfg, seen)
    opened = handle_manifests([downloads], store, cfg, seen)
    assert opened == []
    assert store.already_opened_manifest(file_hash(downloads / "manifest-abc.json"))
