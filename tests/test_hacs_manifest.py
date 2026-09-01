"""Rules for hacs.json, from https://hacs.xyz/docs/publish/start."""
import json
from pathlib import Path

HACS_JSON = Path(__file__).parent.parent / "hacs.json"

# The full set of keys HACS documents. Anything else is silently ignored, which
# makes a typo or a retired key (render_readme, once) invisible until someone
# wonders why the setting has no effect.
SUPPORTED_KEYS = {
    "name",
    "content_in_root",
    "zip_release",
    "filename",
    "hide_default_branch",
    "country",
    "homeassistant",
    "hacs",
    "persistent_directory",
}

# entry.runtime_data and ConfigEntry[T] both landed in 2024.6.0 and are absent
# in 2024.5.0. Declaring anything lower lets HACS install onto a Home Assistant
# that raises AttributeError during setup.
MINIMUM_SUPPORTABLE = (2024, 6, 0)


def _load():
    return json.loads(HACS_JSON.read_text())


def _version_tuple(raw):
    return tuple(int(part) for part in raw.split("."))


def test_hacs_json_declares_a_name():
    assert _load().get("name")


def test_hacs_json_uses_only_documented_keys():
    unknown = set(_load()) - SUPPORTED_KEYS
    assert not unknown, f"not documented by HACS: {sorted(unknown)}"


def test_declared_ha_floor_is_actually_supportable():
    """The declared minimum must not promise support the code cannot deliver."""
    declared = _load().get("homeassistant")
    assert declared, "hacs.json must pin a minimum Home Assistant version"
    assert _version_tuple(declared) >= MINIMUM_SUPPORTABLE, (
        f"declared {declared}, but the integration needs at least "
        f"{'.'.join(map(str, MINIMUM_SUPPORTABLE))} for entry.runtime_data"
    )
