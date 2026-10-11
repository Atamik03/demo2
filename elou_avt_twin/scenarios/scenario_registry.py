"""
scenario_registry.py
====================
Scenario library of the simulator core.

The built-in demo scenarios were removed on request — only instructor-authored
scenarios (lms_scenarios in the content store) are used now. They are converted
to engine `Scenario` objects at runtime by `lms.scenario_service.to_engine_scenario`
and loaded through `DigitalTwin.load_scenario_object`.
"""

from models.scenario import Scenario
from typing import Dict


def build_scenarios() -> Dict[str, Scenario]:
    return {}


SCENARIO_REGISTRY: Dict[str, Scenario] = build_scenarios()
