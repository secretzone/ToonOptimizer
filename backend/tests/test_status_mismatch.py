"""Unit tests for the /api/status mismatch computation (toonopt.api.status)."""
from __future__ import annotations

from toonopt.api.status import _version_patch, mismatch_status


def test_version_patch_drops_trailing_build_number():
    assert _version_patch("12.1.0.69875") == "12.1.0"
    assert _version_patch("12.1.0") == "12.1.0"
    assert _version_patch("garbage") == "garbage"


def test_mismatch_simc_ignores_build_number_only_difference():
    simc = {"wow_version": "12.1.0.60000"}
    m = mismatch_status(simc, "12.1.0.69875", "12.1.0.69875")
    assert m["simc"] is False
    assert m["simc_wow_version"] == "12.1.0.60000"
    assert m["game_build"] == "12.1.0.69875"


def test_mismatch_simc_flags_different_patch():
    simc = {"wow_version": "12.0.0.69875"}
    m = mismatch_status(simc, "12.1.0.69875", "")
    assert m["simc"] is True


def test_mismatch_simc_false_when_not_installed():
    m = mismatch_status({"wow_version": ""}, "12.1.0.69875", "")
    assert m["simc"] is False


def test_mismatch_data_flags_stale_cache():
    simc = {"wow_version": "12.1.0.69875"}
    m = mismatch_status(simc, "12.1.0.69875", "12.0.0.60000")
    assert m["data"] is True
    assert m["data_build"] == "12.0.0.60000"


def test_mismatch_data_false_when_cache_matches_or_empty():
    simc = {"wow_version": "12.1.0.69875"}
    assert mismatch_status(simc, "12.1.0.69875", "12.1.0.69875")["data"] is False
    assert mismatch_status(simc, "12.1.0.69875", "")["data"] is False
