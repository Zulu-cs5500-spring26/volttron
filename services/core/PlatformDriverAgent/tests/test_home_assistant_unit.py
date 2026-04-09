# -*- coding: utf-8 -*- {{{
# ===----------------------------------------------------------------------===
#
#                 Component of Eclipse VOLTTRON
#
# ===----------------------------------------------------------------------===
#
# Copyright 2023 Battelle Memorial Institute
#
# Licensed under the Apache License, Version 2.0 (the "License"); you may not
# use this file except in compliance with the License. You may obtain a copy
# of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS, WITHOUT
# WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied. See the
# License for the specific language governing permissions and limitations
# under the License.
#
# ===----------------------------------------------------------------------===
# }}}

"""Unit tests for the Home Assistant Driver interface.

These tests do **not** require a running Home Assistant or Volttron platform.
They mock ``requests.post`` / ``requests.get`` to verify that the driver
dispatches each supported entity type to the correct HA REST endpoint with
the expected payload.

Run with::

    pytest services/core/PlatformDriverAgent/tests/test_home_assistant_unit.py
"""

from unittest.mock import MagicMock, patch

import pytest

from platform_driver.interfaces.home_assistant import (
    HomeAssistantRegister,
    Interface,
)


def _make_register(entity_id, entity_point="state", reg_type=int, read_only=False):
    """Build a register without going through ``parse_config``."""
    return HomeAssistantRegister(
        read_only=read_only,
        pointName="p",
        units="",
        reg_type=reg_type,
        attributes={},
        entity_id=entity_id,
        entity_point=entity_point,
    )


@pytest.fixture
def iface():
    """Minimal Interface instance with network config set but no HA connection.

    Bypasses ``__init__`` so we don't need a full Volttron platform; only the
    attributes required by the helper methods are populated.
    """
    instance = object.__new__(Interface)
    instance.ip_address = "127.0.0.1"
    instance.port = 8123
    instance.access_token = "test_token"
    instance.units = "F"
    instance.point_name = None
    return instance


def _bind_register(iface, register):
    """Monkey-patch register lookup so ``_set_point`` finds our test register."""
    iface.get_register_by_name = lambda name: register


def _bind_registers_for_scrape(iface, register):
    """Monkey-patch register enumeration so ``_scrape_all`` sees our register."""
    iface.get_registers_by_type = lambda _type, read_only: (
        [register] if not read_only else []
    )


# ---------------------------------------------------------------------------
# _set_point dispatch: verifies the right HA service endpoint is hit
# ---------------------------------------------------------------------------


@patch("platform_driver.interfaces.home_assistant.requests.post")
class TestSetPointDispatch:
    def _ok(self, mock_post):
        mock_post.return_value = MagicMock(status_code=200, text="ok")

    # ---- switch ----------------------------------------------------------

    def test_switch_on(self, mock_post, iface):
        self._ok(mock_post)
        _bind_register(iface, _make_register("switch.kitchen"))
        iface._set_point("p", 1)
        url = mock_post.call_args.args[0]
        payload = mock_post.call_args.kwargs["json"]
        assert "/api/services/switch/turn_on" in url
        assert payload == {"entity_id": "switch.kitchen"}

    def test_switch_off(self, mock_post, iface):
        self._ok(mock_post)
        _bind_register(iface, _make_register("switch.kitchen"))
        iface._set_point("p", 0)
        assert "/api/services/switch/turn_off" in mock_post.call_args.args[0]

    def test_switch_invalid_value_raises(self, mock_post, iface):
        _bind_register(iface, _make_register("switch.kitchen"))
        with pytest.raises(ValueError, match="should be an integer"):
            iface._set_point("p", 5)
        mock_post.assert_not_called()

    # ---- fan -------------------------------------------------------------

    def test_fan_on(self, mock_post, iface):
        self._ok(mock_post)
        _bind_register(iface, _make_register("fan.ceiling"))
        iface._set_point("p", 1)
        assert "/api/services/fan/turn_on" in mock_post.call_args.args[0]
        assert mock_post.call_args.kwargs["json"] == {"entity_id": "fan.ceiling"}

    def test_fan_off(self, mock_post, iface):
        self._ok(mock_post)
        _bind_register(iface, _make_register("fan.ceiling"))
        iface._set_point("p", 0)
        assert "/api/services/fan/turn_off" in mock_post.call_args.args[0]

    def test_fan_invalid_value_raises(self, mock_post, iface):
        _bind_register(iface, _make_register("fan.ceiling"))
        with pytest.raises(ValueError, match="should be an integer"):
            iface._set_point("p", 2)
        mock_post.assert_not_called()

    # ---- cover -----------------------------------------------------------

    def test_cover_open(self, mock_post, iface):
        self._ok(mock_post)
        _bind_register(iface, _make_register("cover.blinds", reg_type=str))
        iface._set_point("p", "open")
        assert "/api/services/cover/open_cover" in mock_post.call_args.args[0]

    def test_cover_close(self, mock_post, iface):
        self._ok(mock_post)
        _bind_register(iface, _make_register("cover.blinds", reg_type=str))
        iface._set_point("p", "close")
        assert "/api/services/cover/close_cover" in mock_post.call_args.args[0]

    def test_cover_position_valid(self, mock_post, iface):
        self._ok(mock_post)
        _bind_register(
            iface, _make_register("cover.blinds", entity_point="position")
        )
        iface._set_point("p", 75)
        url = mock_post.call_args.args[0]
        payload = mock_post.call_args.kwargs["json"]
        assert "/api/services/cover/set_cover_position" in url
        assert payload["entity_id"] == "cover.blinds"
        assert payload["position"] == 75

    def test_cover_position_out_of_range_raises(self, mock_post, iface):
        _bind_register(
            iface, _make_register("cover.blinds", entity_point="position")
        )
        with pytest.raises(ValueError, match="between 0 and 100"):
            iface._set_point("p", 150)
        mock_post.assert_not_called()

    def test_cover_invalid_state_raises(self, mock_post, iface):
        self._ok(mock_post)
        _bind_register(iface, _make_register("cover.blinds", reg_type=str))
        with pytest.raises(ValueError, match="Invalid cover state"):
            iface._set_point("p", "tilt")
        mock_post.assert_not_called()

    # ---- light & input_boolean backward compatibility --------------------

    def test_light_backward_compat_on(self, mock_post, iface):
        self._ok(mock_post)
        _bind_register(iface, _make_register("light.lamp"))
        iface._set_point("p", 1)
        assert "/api/services/light/turn_on" in mock_post.call_args.args[0]

    def test_input_boolean_backward_compat_off(self, mock_post, iface):
        self._ok(mock_post)
        _bind_register(iface, _make_register("input_boolean.flag"))
        iface._set_point("p", 0)
        assert "/api/services/input_boolean/turn_off" in mock_post.call_args.args[0]

    # ---- unsupported entity ---------------------------------------------

    def test_unsupported_entity_raises(self, mock_post, iface):
        _bind_register(iface, _make_register("sensor.outside_temp"))
        with pytest.raises(ValueError, match="Unsupported entity_id"):
            iface._set_point("p", 1)
        mock_post.assert_not_called()


# ---------------------------------------------------------------------------
# _scrape_all read path: regression tests for the short-circuit bug (#28)
# that previously made cover reads unreachable
# ---------------------------------------------------------------------------


@patch("platform_driver.interfaces.home_assistant.requests.get")
class TestScrapeAllReadPath:
    def _mock_state(self, mock_get, state, attributes=None):
        mock_get.return_value = MagicMock(
            status_code=200,
            json=lambda: {"state": state, "attributes": attributes or {}},
        )

    def test_cover_state_reads_through(self, mock_get, iface):
        """Regression: before #28 was fixed, cover reads were swallowed by the
        light/input_boolean branch because of a short-circuit ``or``."""
        reg = _make_register("cover.blinds", entity_point="state", reg_type=str)
        _bind_registers_for_scrape(iface, reg)
        self._mock_state(mock_get, "open")
        result = iface._scrape_all()
        assert result[reg.point_name] == "open"

    def test_cover_position_reads_from_attributes(self, mock_get, iface):
        reg = _make_register("cover.blinds", entity_point="position")
        _bind_registers_for_scrape(iface, reg)
        self._mock_state(mock_get, "open", {"current_position": 42})
        result = iface._scrape_all()
        assert result[reg.point_name] == 42

    def test_switch_state_on_becomes_1(self, mock_get, iface):
        reg = _make_register("switch.outlet")
        _bind_registers_for_scrape(iface, reg)
        self._mock_state(mock_get, "on")
        result = iface._scrape_all()
        assert result[reg.point_name] == 1

    def test_fan_state_off_becomes_0(self, mock_get, iface):
        reg = _make_register("fan.ceiling")
        _bind_registers_for_scrape(iface, reg)
        self._mock_state(mock_get, "off")
        result = iface._scrape_all()
        assert result[reg.point_name] == 0

    def test_light_state_backward_compat(self, mock_get, iface):
        reg = _make_register("light.lamp")
        _bind_registers_for_scrape(iface, reg)
        self._mock_state(mock_get, "on")
        result = iface._scrape_all()
        assert result[reg.point_name] == 1


# ---------------------------------------------------------------------------
# Helper methods: verify the low-level URL + payload shape
# ---------------------------------------------------------------------------


@patch("platform_driver.interfaces.home_assistant.requests.post")
class TestHelperMethods:
    def _ok(self, mock_post):
        mock_post.return_value = MagicMock(status_code=200, text="ok")

    def test_set_switch_constructs_correct_request(self, mock_post, iface):
        self._ok(mock_post)
        iface.set_switch("switch.x", "on")
        assert mock_post.call_args.args[0] == (
            "http://127.0.0.1:8123/api/services/switch/turn_on"
        )
        assert mock_post.call_args.kwargs["json"] == {"entity_id": "switch.x"}
        assert (
            mock_post.call_args.kwargs["headers"]["Authorization"]
            == "Bearer test_token"
        )

    def test_set_fan_constructs_correct_request(self, mock_post, iface):
        self._ok(mock_post)
        iface.set_fan("fan.x", "off")
        assert mock_post.call_args.args[0] == (
            "http://127.0.0.1:8123/api/services/fan/turn_off"
        )

    def test_set_cover_state_invalid_raises(self, mock_post, iface):
        with pytest.raises(ValueError, match="Invalid cover state"):
            iface.set_cover_state("cover.x", "halfway")
        mock_post.assert_not_called()

    def test_set_cover_position_non_integer_raises(self, mock_post, iface):
        with pytest.raises(ValueError, match="must be a number"):
            iface.set_cover_position("cover.x", "halfway")
        mock_post.assert_not_called()

    def test_set_cover_position_out_of_range_raises(self, mock_post, iface):
        with pytest.raises(ValueError, match="between 0 and 100"):
            iface.set_cover_position("cover.x", 200)
        mock_post.assert_not_called()
