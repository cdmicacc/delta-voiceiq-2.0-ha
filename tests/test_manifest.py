"""Manifest rules that hassfest enforces, checked locally for fast feedback."""
import json
from pathlib import Path

MANIFEST = (
    Path(__file__).parent.parent
    / "custom_components"
    / "delta_voiceiq"
    / "manifest.json"
)


def test_manifest_keys_are_sorted_the_way_hassfest_requires():
    """domain and name first, everything else alphabetical."""
    keys = list(json.loads(MANIFEST.read_text()))

    assert keys[:2] == ["domain", "name"]
    assert keys[2:] == sorted(keys[2:])


def test_manifest_declares_the_keys_hacs_requires():
    """HACS requires these six keys on a custom integration manifest."""
    manifest = json.loads(MANIFEST.read_text())

    for key in ("domain", "documentation", "issue_tracker", "codeowners", "name", "version"):
        assert manifest.get(key), f"{key} missing or empty in manifest.json"
