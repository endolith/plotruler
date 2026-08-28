"""PyInstaller entry point for PlotRuler.

PyInstaller executes this file as a top-level script, so the package's
__main__.py cannot use relative imports. This launcher imports the
package's entry point by its real module name and runs it.
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from plotruler.__main__ import main

if __name__ == "__main__":
    main()
