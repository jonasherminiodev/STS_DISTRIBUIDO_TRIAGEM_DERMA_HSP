#!/usr/bin/env bash
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
WORKSPACE_ROOT="$(dirname "$SCRIPT_DIR")"
VENV_PKGS="$WORKSPACE_ROOT/ANALISE_IMG_CANCER_DE_PELE /.venv/lib/python3.9/site-packages"

export PYTHONPATH="$VENV_PKGS:$SCRIPT_DIR:$PYTHONPATH"
python3 "$SCRIPT_DIR/run_gateway.py" "$@"
