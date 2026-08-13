"""PyInstaller entry point for the CFIX Gateway desktop app.

Imports cfix_api.gui.app with an absolute import so PyInstaller's static
analysis (which walks imports starting from whatever script it's pointed
at) never has to resolve app.py's own relative imports (`from .log_handler
import ...`) directly against a script run outside its package - the same
class of problem `python app.py` hits, avoided here by never treating
app.py itself as the entry point.

Requires cfix_api to be installed first (`pip install -e .[gui]` from the
repo root) so this import resolves.
"""

import sys

from cfix_api.gui.app import main

if __name__ == "__main__":
    sys.exit(main())
