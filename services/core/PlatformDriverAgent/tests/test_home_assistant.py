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

import json
import logging
import pytest
import gevent

from volttron.platform.agent.known_identities import (
    PLATFORM_DRIVER,
    CONFIGURATION_STORE,
)
from volttron.platform import get_services_core
from volttron.platform.agent import utils
from volttron.platform.keystore import KeyStore
from volttrontesting.utils.platformwrapper import PlatformWrapper

utils.setup_logging()
logger = logging.getLogger(__name__)

# To run these tests, set up a Home Assistant instance with the following test entities:
#
# 1. Create a helper toggle named `volttrontest`:
#    Settings > Devices & services > Helpers > Create Helper > Toggle > name "volttrontest"
#
# 2. Add the following to your HA configuration.yaml to create template switch/fan/cover
#    entities backed by helpers (so the tests can exercise the switch/fan/cover dispatch
#    paths without requiring real hardware):
#
#    input_boolean:
#      vt_switch_backing:
#      vt_fan_backing:
#      vt_cover_backing:
#
#    switch:
#      - platform: template
#        switches:
#          volttrontest:
#            value_template: "{{ is_state('input_boolean.vt_switch_backing', 'on') }}"
#            turn_on:
#              service: input_boolean.turn_on
#              target: {entity_id: input_boolean.vt_switch_backing}
#            turn_off:
#              service: input_boolean.turn_off
#              target: {entity_id: input_boolean.vt_switch_backing}
#
#    fan:
#      - platform: template
#        fans:
#          volttrontest:
#            value_template: "{{ is_state('input_boolean.vt_fan_backing', 'on') }}"
#            turn_on:
#              service: input_boolean.turn_on
#              target: {entity_id: input_boolean.vt_fan_backing}
#            turn_off:
#              service: input_boolean.turn_off
#              target: {entity_id: input_boolean.vt_fan_backing}
#
#    cover:
#      - platform: template
#        covers:
#          volttrontest:
#            value_template: "{{ is_state('input_boolean.vt_cover_backing', 'on') }}"
#            open_cover:
#              service: input_boolean.turn_on
#              target: {entity_id: input_boolean.vt_cover_backing}
#            close_cover:
#              service: input_boolean.turn_off
#              target: {entity_id: input_boolean.vt_cover_backing}
#
# 3. Restart Home Assistant, then fill in the three variables below and run:
#    pytest services/core/PlatformDriverAgent/tests/test_home_assistant.py -v
HOMEASSISTANT_TEST_IP = ""
ACCESS_TOKEN = ""
PORT = ""

skip_msg = "Some configuration variables are not set. Check HOMEASSISTANT_TEST_IP, ACCESS_TOKEN, and PORT"

# Skip tests if variables are not set
pytestmark = pytest.mark.skipif(
    not (HOMEASSISTANT_TEST_IP and ACCESS_TOKEN and PORT),
    reason=skip_msg
)
HOMEASSISTANT_DEVICE_TOPIC = "devices/home_assistant"


# Get the point which will should be off
def test_get_point(volttron_instance, config_store):
    expected_values = 0
    agent = volttron_instance.dynamic_agent
    result = agent.vip.rpc.call(PLATFORM_DRIVER, 'get_point', 'home_assistant', 'bool_state').get(timeout=20)
    assert result == expected_values, "The result does not match the expected result."


# The default value for this fake light is 3. If the test cannot reach out to home assistant,
# the value will default to 3 making the test fail.
def test_data_poll(volttron_instance: PlatformWrapper, config_store):
    expected_values = [{'bool_state': 0}, {'bool_state': 1}]
    agent = volttron_instance.dynamic_agent
    result = agent.vip.rpc.call(PLATFORM_DRIVER, 'scrape_all', 'home_assistant').get(timeout=20)
    assert result in expected_values, "The result does not match the expected result."


# Turn on the light. Light is automatically turned off every 30 seconds to allow test to turn
# it on and receive the correct value.
def test_set_point(volttron_instance, config_store):
    expected_values = {'bool_state': 1,
                       'switch_state': 0, 'fan_state': 0, 'cover_state': 0}
    agent = volttron_instance.dynamic_agent
    agent.vip.rpc.call(PLATFORM_DRIVER, 'set_point', 'home_assistant', 'bool_state', 1)
    gevent.sleep(10)
    result = agent.vip.rpc.call(PLATFORM_DRIVER, 'scrape_all', 'home_assistant').get(timeout=20)
    assert result == expected_values, "The result does not match the expected result."


# Set the switch on via Volttron, then read it back through scrape_all.
# Exercises the new switch dispatch branch + the _scrape_all bug fix on the read path.
def test_switch_set_and_read(volttron_instance, config_store):
    agent = volttron_instance.dynamic_agent
    agent.vip.rpc.call(PLATFORM_DRIVER, 'set_point',
                       'home_assistant', 'switch_state', 1).get(timeout=20)
    gevent.sleep(3)
    result = agent.vip.rpc.call(PLATFORM_DRIVER, 'scrape_all',
                                'home_assistant').get(timeout=20)
    assert result['switch_state'] == 1, \
        "switch.volttrontest should be on after set_point(switch_state, 1)"

    # turn it off again to leave the instance clean for the next test
    agent.vip.rpc.call(PLATFORM_DRIVER, 'set_point',
                       'home_assistant', 'switch_state', 0).get(timeout=20)
    gevent.sleep(2)
    result = agent.vip.rpc.call(PLATFORM_DRIVER, 'scrape_all',
                                'home_assistant').get(timeout=20)
    assert result['switch_state'] == 0


# Same loop for fan.volttrontest.
def test_fan_set_and_read(volttron_instance, config_store):
    agent = volttron_instance.dynamic_agent
    agent.vip.rpc.call(PLATFORM_DRIVER, 'set_point',
                       'home_assistant', 'fan_state', 1).get(timeout=20)
    gevent.sleep(3)
    result = agent.vip.rpc.call(PLATFORM_DRIVER, 'scrape_all',
                                'home_assistant').get(timeout=20)
    assert result['fan_state'] == 1, \
        "fan.volttrontest should be on after set_point(fan_state, 1)"

    agent.vip.rpc.call(PLATFORM_DRIVER, 'set_point',
                       'home_assistant', 'fan_state', 0).get(timeout=20)
    gevent.sleep(2)


# Cover uses open/close semantics: set_point(100) -> open, set_point(0) -> closed.
def test_cover_set_and_read(volttron_instance, config_store):
    agent = volttron_instance.dynamic_agent
    agent.vip.rpc.call(PLATFORM_DRIVER, 'set_point',
                       'home_assistant', 'cover_state', 100).get(timeout=20)
    gevent.sleep(3)
    result = agent.vip.rpc.call(PLATFORM_DRIVER, 'scrape_all',
                                'home_assistant').get(timeout=20)
    assert result['cover_state'] in (1, 100), \
        "cover.volttrontest should be open after set_point(cover_state, 100)"

    agent.vip.rpc.call(PLATFORM_DRIVER, 'set_point',
                       'home_assistant', 'cover_state', 0).get(timeout=20)
    gevent.sleep(2)


# Regression: invalid value must raise before the HTTP call is made.
# This is the behaviour we added in the fix for #28.
def test_invalid_switch_value_is_rejected(volttron_instance, config_store):
    agent = volttron_instance.dynamic_agent
    with pytest.raises(Exception):
        agent.vip.rpc.call(PLATFORM_DRIVER, 'set_point',
                           'home_assistant', 'switch_state', 5).get(timeout=20)


@pytest.fixture(scope="module")
def config_store(volttron_instance, platform_driver):

    capabilities = [{"edit_config_store": {"identity": PLATFORM_DRIVER}}]
    volttron_instance.add_capabilities(volttron_instance.dynamic_agent.core.publickey, capabilities)

    registry_config = "homeassistant_test.json"
    registry_obj = [
        {
            "Entity ID": "input_boolean.volttrontest",
            "Entity Point": "state",
            "Volttron Point Name": "bool_state",
            "Units": "On / Off",
            "Units Details": "off: 0, on: 1",
            "Writable": True,
            "Starting Value": 3,
            "Type": "int",
            "Notes": "lights hallway"
        },
        {
            "Entity ID": "switch.volttrontest",
            "Entity Point": "state",
            "Volttron Point Name": "switch_state",
            "Units": "On / Off",
            "Units Details": "off: 0, on: 1",
            "Writable": True,
            "Starting Value": 0,
            "Type": "int",
            "Notes": "test switch (template-backed)"
        },
        {
            "Entity ID": "fan.volttrontest",
            "Entity Point": "state",
            "Volttron Point Name": "fan_state",
            "Units": "On / Off",
            "Units Details": "off: 0, on: 1",
            "Writable": True,
            "Starting Value": 0,
            "Type": "int",
            "Notes": "test fan (template-backed)"
        },
        {
            "Entity ID": "cover.volttrontest",
            "Entity Point": "state",
            "Volttron Point Name": "cover_state",
            "Units": "Open / Closed",
            "Units Details": "closed: 0, open: 100",
            "Writable": True,
            "Starting Value": 0,
            "Type": "int",
            "Notes": "test cover (template-backed)"
        },
    ]

    volttron_instance.dynamic_agent.vip.rpc.call(CONFIGURATION_STORE,
                                                 "manage_store",
                                                 PLATFORM_DRIVER,
                                                 registry_config,
                                                 json.dumps(registry_obj),
                                                 config_type="json")
    gevent.sleep(2)
    # driver config
    driver_config = {
        "driver_config": {"ip_address": HOMEASSISTANT_TEST_IP, "access_token": ACCESS_TOKEN, "port": PORT},
        "driver_type": "home_assistant",
        "registry_config": f"config://{registry_config}",
        "timezone": "US/Pacific",
        "interval": 30,
    }

    volttron_instance.dynamic_agent.vip.rpc.call(CONFIGURATION_STORE,
                                                 "manage_store",
                                                 PLATFORM_DRIVER,
                                                 HOMEASSISTANT_DEVICE_TOPIC,
                                                 json.dumps(driver_config),
                                                 config_type="json"
                                                 )
    gevent.sleep(2)

    yield platform_driver

    print("Wiping out store.")
    volttron_instance.dynamic_agent.vip.rpc.call(CONFIGURATION_STORE, "manage_delete_store", PLATFORM_DRIVER)
    gevent.sleep(0.1)


@pytest.fixture(scope="module")
def platform_driver(volttron_instance):
    # Start the platform driver agent which would in turn start the bacnet driver
    platform_uuid = volttron_instance.install_agent(
        agent_dir=get_services_core("PlatformDriverAgent"),
        config_file={
            "publish_breadth_first_all": False,
            "publish_depth_first": False,
            "publish_breadth_first": False,
        },
        start=True,
    )
    gevent.sleep(2)  # wait for the agent to start and start the devices
    assert volttron_instance.is_agent_running(platform_uuid)
    yield platform_uuid

    volttron_instance.stop_agent(platform_uuid)
    if not volttron_instance.debug_mode:
        volttron_instance.remove_agent(platform_uuid)
