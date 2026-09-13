"""Actual solver verification; skip only when optional solver/mesher absent."""
import pytest
from cadforge.fea import NominalLoad,solve_cantilever,solver_path
from cadforge.geometry import box


def available():
    pytest.importorskip('gmsh')
    try:return solver_path()
    except RuntimeError:pytest.skip('Optional local CalculiX executable is not installed')


def test_actual_ccx_beam_matches_analytic_and_balances_force(tmp_path):
    available()
    result=solve_cantilever(box(100,10,5),tmp_path,NominalLoad(210000,.3,-10,'Synthetic unit verification'),4)
    analytic=10*100**3/(3*210000*(10*5**3/12))
    assert abs(abs(result['mean_tip_displacement_z_mm'])-analytic)/analytic<.05
    assert result['force_balance_error_n']<1e-3
    assert result['element_count']>100
    assert (tmp_path/'study.frd').exists()


def test_actual_solver_elastic_scaling(tmp_path):
    available()
    soft=solve_cantilever(box(60,10,5),tmp_path/'soft',NominalLoad(100000,.3,-5,'Synthetic unit verification'),4)
    stiff=solve_cantilever(box(60,10,5),tmp_path/'stiff',NominalLoad(200000,.3,-5,'Synthetic unit verification'),4)
    assert soft['mean_tip_displacement_z_mm']/stiff['mean_tip_displacement_z_mm']==pytest.approx(2,rel=1e-4)
