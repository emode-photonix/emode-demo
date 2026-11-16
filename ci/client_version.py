"""Prints the emode client version the notebook's setup cell pins, so the tests use the same one."""

from __future__ import annotations

import json
import re
from pathlib import Path

NOTEBOOK = Path(__file__).parent.parent / 'EMode_demo.ipynb'

source = ''.join(''.join(cell['source']) for cell in json.loads(NOTEBOOK.read_text())['cells'])
print(re.search(r"^EMODE_CLIENT = '([^']+)'", source, re.MULTILINE).group(1))
