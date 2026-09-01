"""Every step, error and abort reason the flows emit must have a translation."""
import json
from pathlib import Path

import pytest

COMPONENT = Path(__file__).parent.parent / "custom_components" / "delta_voiceiq"
STRINGS = COMPONENT / "strings.json"
EN = COMPONENT / "translations" / "en.json"


def _load(path):
    return json.loads(path.read_text())


def test_english_translations_match_strings():
    """translations/en.json is the shipped copy of strings.json; they must agree."""
    assert _load(STRINGS) == _load(EN)


@pytest.mark.parametrize("path", [STRINGS, EN])
@pytest.mark.parametrize(
    "keys",
    [
        ("issues", "expiring_soon", "fix_flow", "step", "provider", "data", "provider"),
        ("issues", "expiring_soon", "fix_flow", "step", "code", "data", "code"),
        ("issues", "expiring_soon", "fix_flow", "error", "invalid_code"),
        ("issues", "expiring_soon", "fix_flow", "error", "cannot_connect"),
        ("issues", "expiring_soon", "fix_flow", "abort", "no_devices_found"),
        ("issues", "expiring_soon", "fix_flow", "abort", "entry_not_found"),
    ],
)
def test_repair_fix_flow_strings_exist(path, keys):
    node = _load(path)
    for key in keys:
        assert key in node, f"{'.'.join(keys)} missing from {path.name}"
        node = node[key]
    assert isinstance(node, str) and node.strip()


@pytest.mark.parametrize("path", [STRINGS, EN])
def test_expiring_soon_title_reports_the_day_count(path):
    """The days placeholder belongs in the title -- fixable issues show that, not
    the description, so the count has to survive there."""
    assert "{days}" in _load(path)["issues"]["expiring_soon"]["title"]


@pytest.mark.parametrize("path", [STRINGS, EN])
def test_fixable_issue_does_not_also_define_a_description(path):
    """Hassfest treats description and fix_flow as mutually exclusive.

    An issue is either fixable (fix_flow, whose first step supplies the text) or
    static (description). Defining both fails validation with "two or more values
    in the same group of exclusion 'fixable'".
    """
    issue = _load(path)["issues"]["expiring_soon"]
    assert "fix_flow" in issue
    assert "description" not in issue


@pytest.mark.parametrize("path", [STRINGS, EN])
def test_expiring_soon_does_not_send_users_to_a_dead_end(path):
    """There is no manual reauth entry point on the integration page, so the old
    'go to Settings and reauthenticate' instruction pointed nowhere."""
    issue = _load(path)["issues"]["expiring_soon"]
    text = f"{issue['title']} {issue.get('description', '')}"
    assert "Devices & Services" not in text
