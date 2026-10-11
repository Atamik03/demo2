from lms.orbita_scenario_catalog import CATALOG
from lms.orbita_task_library import TASKS


def test_task_library_references_existing_orbita_scenarios():
    scenario_titles = {item["title"] for item in CATALOG}
    assert len(TASKS) >= 10
    assert all(item["scenario_title"] in scenario_titles for item in TASKS)
    assert len({item["title"] for item in TASKS}) == len(TASKS)
