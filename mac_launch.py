#!/usr/bin/env python3
"""Launch normally; select and authorize USB inside the application window."""
import sys

if sys.platform != 'darwin':
    raise SystemExit('Ten skrypt jest przeznaczony dla macOS.')

from teslarecover.__main__ import main

if __name__ == '__main__':
    main()
