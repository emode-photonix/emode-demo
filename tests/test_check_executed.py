"""Tests of ci/check_executed.py, the nightly run's verdict on the executed notebook."""

from __future__ import annotations

import importlib.util
from pathlib import Path

spec = importlib.util.spec_from_file_location(
    'check_executed', Path(__file__).parent.parent / 'ci' / 'check_executed.py'
)
check_executed = importlib.util.module_from_spec(spec)
spec.loader.exec_module(check_executed)

FIGURE = {'output_type': 'display_data', 'data': {'image/png': 'iVBOR'}}


def notebook(*outputs: list[dict]) -> dict:
    return {'cells': [{'cell_type': 'code', 'outputs': list(o)} for o in outputs]}


def error(ename: str) -> dict:
    return {'output_type': 'error', 'ename': ename, 'evalue': 'why', 'traceback': []}


def test_every_cell_ran():
    code, message = check_executed.check(notebook([], [FIGURE], [FIGURE], [FIGURE], []))
    assert code == 0
    assert '3 figures' in message


def test_paused_passes_with_a_notice():
    # --allow-errors runs on past the setup cell, so later cells fail too.
    code, message = check_executed.check(notebook([error('DemoPaused')], [error('NameError')]))
    assert code == 0
    assert message.startswith('::notice::')


def test_any_other_error_fails():
    code, message = check_executed.check(notebook([FIGURE], [error('DemoStop')]))
    assert code == 1
    assert 'DemoStop' in message


def test_missing_figures_fail():
    code, message = check_executed.check(notebook([], [FIGURE], []))
    assert code == 1
    assert 'figures' in message
