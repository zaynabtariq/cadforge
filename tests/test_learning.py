import dataclasses
import pytest

from cadforge.skills import Evidence, ParameterCommand, SkillLibrary


def candidate(library, name="wall", parents=()):
    return library.propose(name, [ParameterCommand("wall", "at_least", 2)],
                           [Evidence("dev-discovery", "development", False, ("thin_wall",))], parents)


def promote(library, skill):
    return library.promote(skill.id, [Evidence("dev-regression", "development", True)])


def test_parameterized_repair_transfers_to_different_dimensions():
    cmd = ParameterCommand("width", "at_least", 4, "board_width")
    assert cmd.apply({"width": 10, "board_width": 30})["width"] == 34
    assert cmd.apply({"width": 10, "board_width": 52})["width"] == 56


def test_hidden_evidence_never_accepted():
    lib = SkillLibrary()
    with pytest.raises(ValueError, match="development"):
        lib.propose("leak", [ParameterCommand("wall", "set", 3)],
                    [Evidence("hidden-1", "hidden", False, ("wall",))])
    skill = candidate(lib)
    with pytest.raises(ValueError, match="development"):
        lib.promote(skill.id, [Evidence("hidden-1", "hidden", True)])


def test_independent_regression_and_immutable_versions(tmp_path):
    lib = SkillLibrary()
    skill = candidate(lib)
    with pytest.raises(ValueError, match="candidate"):
        lib.compose(skill.id, {"wall": 1})
    with pytest.raises(ValueError, match="independent"):
        lib.promote(skill.id, [Evidence("dev-discovery", "development", True)])
    with pytest.raises(ValueError, match="pass"):
        lib.promote(skill.id, [Evidence("regression", "development", False, ("thin_wall",))])
    promoted = promote(lib, skill)
    with pytest.raises(dataclasses.FrozenInstanceError):
        promoted.name = "mutated"
    path = tmp_path / "skills.json"
    lib.save(path)
    assert SkillLibrary.load(path).compose(skill.id, {"wall": 1}) == {"wall": 2}


def test_inheritance_dag_shared_parent_runs_once_and_cycles_fail():
    lib = SkillLibrary()
    root = lib.propose("add", [ParameterCommand("wall", "add", 1)],
                       [Evidence("d", "development", False, ("thin_wall",))])
    promote(lib, root)
    left = promote(lib, candidate(lib, "left", (root.id,)))
    right = promote(lib, candidate(lib, "right", (root.id,)))
    child = promote(lib, candidate(lib, "child", (left.id, right.id)))
    assert lib.compose(child.id, {"wall": 5})["wall"] == 6
    # Simulate corrupt in-memory graph; traversal must still reject a cycle.
    lib._skills[root.id] = dataclasses.replace(lib._skills[root.id], parent_ids=(child.id,))
    with pytest.raises(ValueError, match="cycle"):
        lib.compose(child.id, {"wall": 1})
