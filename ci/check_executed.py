"""Checks a notebook that nbconvert executed with --allow-errors.

Passes when every cell ran without an error and the notebook drew at least
MIN_FIGURES figures. Also passes, with a GitHub Actions notice, when the setup
cell stopped because the demo is paused (DemoPaused): the demo's kill switch is
on, which is not a failure of the notebook. Any other error fails the run.

    python ci/check_executed.py executed.ipynb
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

MIN_FIGURES = 3  # em.plot() in part 1, the field plot in part 2, the sweep in part 3


def check(notebook: dict) -> tuple[int, str]:
    """The exit code and the message for an executed notebook."""
    figures = 0
    for index, cell in enumerate(notebook['cells']):
        if cell['cell_type'] != 'code':
            continue
        for output in cell.get('outputs', []):
            if output['output_type'] == 'error':
                if output['ename'] == 'DemoPaused':
                    return 0, f'::notice::The EMode demo is paused: {output["evalue"]}'
                return 1, f'::error::Cell {index} raised {output["ename"]}: {output["evalue"]}'
            if 'image/png' in output.get('data', {}):
                figures += 1
    if figures < MIN_FIGURES:
        return 1, f'::error::The notebook drew {figures} figures, expected at least {MIN_FIGURES}.'
    return 0, f'Every cell ran, {figures} figures drawn.'


def main() -> int:
    code, message = check(json.loads(Path(sys.argv[1]).read_text()))
    print(message)
    return code


if __name__ == '__main__':
    sys.exit(main())
