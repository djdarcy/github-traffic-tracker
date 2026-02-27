"""Allow running as: python -m ghtraf"""

import sys

from ghtraf.cli import main

if __name__ == "__main__":
    sys.exit(main())
