from pathlib import Path

from context_note.watch import looks_like_export


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
