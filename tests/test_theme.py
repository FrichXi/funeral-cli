"""Tests for terminal theme/background detection helpers."""

from __future__ import annotations

from funeralai.tui.theme import _normalize_osc_channel, _parse_osc11_response


def test_normalize_osc_channel_scales_four_digit_hex():
    assert _normalize_osc_channel("ffff") == 255
    assert _normalize_osc_channel("0000") == 0
    assert _normalize_osc_channel("8080") == 128


def test_parse_osc11_response_for_light_background():
    response = "\x1b]11;rgb:ffff/ffff/ffff\x1b\\"
    assert _parse_osc11_response(response) == ("light", "#ffffff")


def test_parse_osc11_response_for_dark_background_with_bel():
    response = "\x1b]11;rgb:0000/0000/0000\x07"
    assert _parse_osc11_response(response) == ("dark", "#000000")
