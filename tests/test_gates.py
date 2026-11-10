"""四个流程开关（第二版计划 1 Task 2）。"""

import dataclasses

import pytest

from cad_agent.gates import Gates


def test_gates_default_all_on():
    g = Gates()
    assert (g.staged, g.mutation_check, g.visual_review, g.cases) == (True, True, True, True)


def test_gates_legacy_all_off():
    g = Gates.legacy()
    assert (g.staged, g.mutation_check, g.visual_review, g.cases) == (False, False, False, False)
    assert g == Gates(staged=False, mutation_check=False, visual_review=False, cases=False)


def test_gates_are_frozen():
    with pytest.raises(dataclasses.FrozenInstanceError):
        Gates().staged = False  # type: ignore[misc]
