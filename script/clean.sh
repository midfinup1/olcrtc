#!/bin/bash
set -euo pipefail

rm -rf build dist
rm -rf app/__pycache__ __pycache__ .pytest_cache
find . -name ".DS_Store" -delete
find . -name "__MACOSX" -type d -prune -exec rm -rf {} +
