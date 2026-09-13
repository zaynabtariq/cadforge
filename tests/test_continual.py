"""Synthetic unit checks for learning mechanics, not physical CAD evidence."""
import hashlib
import sqlite3
import pytest

from cadforge.continual import Case, Context, ContinualLearning, Measurement


CONTEXT = Context("unit-test synthetic", "ideal geometry", {"fixture": "1"}, "checks-1", "recipe-1")


def case(name, x=3., clearance=.2, task="discovery", **extra):
    return Case(name, task, {"fastener_diameter": x, "radial_clearance": clearance,
                            "bore_diameter": 0., **extra}, hashlib.sha256(task.encode()).hexdigest())


def execute(parameters, case_id):
    required = parameters["fastener_diameter"] + 2 * parameters["radial_clearance"]
    passed = parameters["bore_diameter"] >= required - 1e-7
    return Measurement(passed, {"bore_diameter": required}, () if passed else ("bore_interference",),
                       {"screw_clearance": passed})


def discover(service, prefix="bore", executor=execute, parents=()):
    experiments = [service.run_experiment(case(f"{prefix}-d{i}", x, c), executor,
                                          stage="discovery", context=CONTEXT)
                   for i, (x, c) in enumerate([(2., .1), (3., .2), (4., .1), (5., .3)])]
    return service.propose_affine("bore", "bore_diameter", ["fastener_diameter", "radial_clearance"],
                                  experiments, parent_ids=parents)


def validate(service, identifier, prefix="bore", executor=execute):
    service.validate_candidate(identifier, [case(f"{prefix}-challenge", 2.5, .15)], executor,
                               stage="counterexample", context=CONTEXT)
    service.validate_candidate(identifier, [case(f"{prefix}-t1", 3.5, .2, "bracket"),
                                            case(f"{prefix}-t2", 4.5, .25, "clip")], executor,
                               stage="transfer", context=CONTEXT)
    return service.promote(identifier)


def test_measured_multivariate_factors_persist_and_execute(tmp_path):
    path = tmp_path / "learning.sqlite"
    service = ContinualLearning(path)
    identifier = discover(service)
    with pytest.raises(ValueError, match="counterexample"):
        service.promote(identifier)
    skill = validate(service, identifier)
    assert skill.commands[1].factor == pytest.approx(1)
    assert skill.commands[2].factor == pytest.approx(2)
    assert service.audit()["experiments"] == 7
    service.close()
    restored = ContinualLearning(path)
    result = restored.apply("bore", case("new-task", 4, .2).parameters, context=CONTEXT)
    assert result["bore_diameter"] == pytest.approx(4.4)
    with pytest.raises(ValueError, match="support"):
        restored.apply("bore", case("extrapolation", 12).parameters, context=CONTEXT)
    with pytest.raises(KeyError, match="context"):
        restored.apply("bore", case("wrong-env").parameters,
                       context=Context("other", "PLA", {"fixture": "1"}, "checks-1", "recipe-1"))


def test_dimensions_and_receipt_share_snapshot_during_concurrent_promotion(tmp_path,monkeypatch):
    path=tmp_path/'learning.sqlite'
    reader=ContinualLearning(path);writer=ContinualLearning(path)
    old=discover(writer,'old');validate(writer,old,'old')
    def revised(p,_):
        required=p['fastener_diameter']+3*p['radial_clearance']
        passed=p['bore_diameter']>=required-1e-7
        return Measurement(passed,{'bore_diameter':required},() if passed else ('fit',),{'fit':passed})
    new=discover(writer,'new',executor=revised)
    original=reader._payload;promoted=False
    def interleaved(table,identifier):
        nonlocal promoted
        if table=='candidates' and identifier==old and not promoted:
            promoted=True
            validate(writer,new,'new',executor=revised)
        return original(table,identifier)
    monkeypatch.setattr(reader,'_payload',interleaved)
    receipt=reader.apply_with_provenance('bore',case('request').parameters,context=CONTEXT)
    assert promoted and receipt['skill_id']==old
    assert receipt['parameters']['bore_diameter']==pytest.approx(3.4)
    later=reader.apply_with_provenance('bore',case('later').parameters,context=CONTEXT)
    assert later['skill_id']==new
    assert later['parameters']['bore_diameter']==pytest.approx(3.6)
    assert not reader.db.in_transaction
    with pytest.raises(ValueError,match='support'):
        reader.apply_with_provenance('bore',case('unsupported',12).parameters,context=CONTEXT)
    assert not reader.db.in_transaction
    reader.close();writer.close()


def test_hidden_v1_and_corrupt_measurement_rejected_before_promotion(tmp_path):
    service = ContinualLearning(tmp_path / "learning.sqlite")
    for bad in [Case("h", "t", {"x": 1}, "a" * 64, split="hidden"),
                Case("v1", "t", {"x": 1}, "a" * 64, corpus="benchmark-v1")]:
        with pytest.raises(ValueError, match="no hidden or v1"):
            service.run_experiment(bad, lambda *_: pytest.fail("must not execute"), stage="discovery", context=CONTEXT)
    experiment = service.run_experiment(case("bad-checks"),
        lambda *_: Measurement(True, {"bore_diameter": 3}, (), {"collision": False}),
        stage="discovery", context=CONTEXT)
    payload = service._payload("experiments", experiment)
    assert not payload["measurement"]["passed"]
    assert "ValueError" in payload["error"]
    with pytest.raises(sqlite3.IntegrityError, match="immutable"):
        service.db.execute("UPDATE experiments SET payload='{}'")


def test_counterexample_quarantines_and_rollback_to_earlier_version(tmp_path):
    service = ContinualLearning(tmp_path / "learning.sqlite")
    old = discover(service, "first")
    validate(service, old, "first")
    new = discover(service, "second")
    validate(service, new, "second")
    assert service.latest_id("bore", context=CONTEXT) == new
    failure = lambda *_: Measurement(False, {}, ("real_regression",), {"fit": False})
    service.validate_candidate(new, [case("new-regression", 3, .2, "monitor")], failure,
                               stage="monitor", context=CONTEXT)
    result = service.apply("bore", case("reuse").parameters, context=CONTEXT)
    assert result["bore_diameter"] == pytest.approx(3.4)
    assert service.audit()["quarantines"] == 1
    assert service.latest_id("bore", context=CONTEXT) == old
    with pytest.raises(ValueError, match="quarantined"):
        service.promote(new)


def test_independent_tasks_and_case_reuse_guard(tmp_path):
    service = ContinualLearning(tmp_path / "learning.sqlite")
    identifier = discover(service)
    with pytest.raises(ValueError, match="independent"):
        service.validate_candidate(identifier, [case("bore-d0")], execute,
                                   stage="counterexample", context=CONTEXT)
    service.validate_candidate(identifier, [case("c")], execute, stage="counterexample", context=CONTEXT)
    service.validate_candidate(identifier, [case("same-task-1"), case("same-task-2")], execute,
                               stage="transfer", context=CONTEXT)
    with pytest.raises(ValueError, match="tasks independent"):
        service.promote(identifier)


def test_nonlinear_relationship_is_not_promoted_as_affine(tmp_path):
    service = ContinualLearning(tmp_path / "learning.sqlite")
    def nonlinear(p, _):
        return Measurement(False, {"bore_diameter": p["fastener_diameter"] ** 2}, ("fit",), {"fit": False})
    with pytest.raises(ValueError, match="unsupported affine"):
        discover(service, executor=nonlinear)


def test_composition_shared_parent_and_transitive_quarantine(tmp_path):
    service = ContinualLearning(tmp_path / "learning.sqlite")
    parent = discover(service, "parent")
    validate(service, parent, "parent")
    child = discover(service, "child", parents=(parent,))
    validate(service, child, "child")
    exp = service.run_experiment(case("composition-failure"), execute, stage="discovery", context=CONTEXT)
    composed = service.propose_composition("drilled_boss", [parent, child], [exp])
    validate(service, composed, "composition")
    assert service.apply("drilled_boss", case("combined").parameters, context=CONTEXT)["bore_diameter"] == pytest.approx(3.4)
    assert set(service.quarantine(parent, "upstream collision regression")) == {parent, child, composed}
    with pytest.raises(KeyError):
        service.apply("drilled_boss", case("after").parameters, context=CONTEXT)
