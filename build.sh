#!/bin/sh
set -eu

python3 -c 'import sys; sys.exit(0 if sys.version_info >= (3, 10) else "kopt requires Python 3.10 or newer")'
