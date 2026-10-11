from lms.orbita_scenario_catalog import (
    ARM_CONTROLLED_IDS,
    CATALOG,
    FIELD_VISIBLE_TAGS,
    validate_catalog,
)


def test_orbita_catalog_matches_current_arm_and_field_configuration():
    """Every required step has a control in the current operator interface."""
    validate_catalog()

    for scenario in CATALOG:
        for action in scenario["actions"]:
            allowed = FIELD_VISIBLE_TAGS if action.actor == "field_operator" else ARM_CONTROLLED_IDS
            assert action.object_id in allowed, scenario["title"]


def test_orbita_catalog_does_not_require_uncontrolled_reserve_equipment():
    for scenario in CATALOG:
        for action in scenario["actions"]:
            assert action.object_id not in {"pum_176", "pum_177"}, scenario["title"]
