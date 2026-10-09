"""
Lets you run the package directly:  python -m jackvm <program>

Python looks for a file called __main__.py when you use `-m <package>`.
All the real work is in main.py.
"""

import sys

from .main import main

sys.exit(main())
