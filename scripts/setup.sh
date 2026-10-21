#!/usr/bin/env bash
# Create .venv with the pipeline's dependencies. Safe to rerun: does nothing once installed.
set -euo pipefail
cd "$(dirname "$0")/.."
command -v uv >/dev/null || curl -LsSf https://astral.sh/uv/install.sh | sh
export PATH="$HOME/.local/bin:$PATH"
[ -x .venv/bin/python ] || uv venv --python 3.13 .venv
.venv/bin/python -c "import tradingagents, yfinance, markdown_it" 2>/dev/null || uv pip install --python .venv/bin/python -r requirements.txt
