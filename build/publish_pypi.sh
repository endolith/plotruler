#!/usr/bin/env bash
# Build and publish the plotruler package to PyPI (run from the repo root).
#
# The wheel is how pip installs the app on any platform, so publishing it
# is the release path for Linux (and for Windows users who prefer pip over
# the .exe). The Windows .exe is a separate artifact built by build/build.py
# and released via GitHub Releases, not PyPI.
#
# Usage:
#   ./build/publish_pypi.sh --check   # build + upload to TestPyPI
#   ./build/publish_pypi.sh           # build + upload to PyPI
#
# Requires: python3, pip, and the 'build' and 'twine' packages.
set -euo pipefail

cd "$(dirname "$0")/.."
ROOT="$(pwd)"
FLAVOR="${1:-}"

# Build sdist and wheel into a clean dist/ so we never upload stale bits.
rm -rf "$ROOT/dist"
python3 -m build

if [ "$FLAVOR" = "--check" ]; then
    echo "Uploading to TestPyPI..."
    python3 -m twine upload --repository testpypi dist/*
else
    echo "Uploading to PyPI..."
    python3 -m twine upload dist/*
fi
