from pathlib import Path

import pytest

from talk_to_me_server.voices.licenses import VoiceLicensePolicy


@pytest.fixture
def policy() -> VoiceLicensePolicy:
    return VoiceLicensePolicy.from_file(Path("master-data/voice-license-policy.json"))


@pytest.mark.parametrize(
    "license_id", ["CC0-1.0", "CC-BY-4.0", "MIT", "Apache-2.0", "Public Domain"]
)
def test_free_license_needs_no_confirmation(policy, license_id) -> None:
    decision = policy.classify(license_id)

    assert decision.freely_redistributable is True
    assert decision.requires_confirmation is False
    assert decision.notice is None


@pytest.mark.parametrize(
    "license_id", [None, "", "unknown", "CC-BY-NC-4.0", "proprietary"]
)
def test_unknown_or_restrictive_license_requires_confirmation(policy, license_id) -> None:
    decision = policy.classify(license_id)

    assert decision.freely_redistributable is False
    assert decision.requires_confirmation is True
    assert decision.notice


def test_license_matching_is_case_and_whitespace_normalized(policy) -> None:
    assert policy.classify("  cc-by-4.0 ").freely_redistributable is True
