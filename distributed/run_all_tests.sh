#!/usr/bin/env bash
# Script para executar toda a suíte de testes automatizados do sistema distribuído.
set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
WORKSPACE_ROOT="$(dirname "$SCRIPT_DIR")"

echo "======================================================================"
echo " EXECUTANDO SUÍTE COMPLETA DE TESTES DO SISTEMA DISTRIBUÍDO"
echo "======================================================================"

python3 "$SCRIPT_DIR/tests/test_proto_serialization.py"
python3 "$SCRIPT_DIR/tests/test_gateway_core.py"
python3 "$SCRIPT_DIR/tests/test_multiprocess_sources.py"
python3 "$SCRIPT_DIR/tests/test_tcp_server_analytics.py"
python3 "$SCRIPT_DIR/tests/test_cli_client.py"
python3 "$SCRIPT_DIR/tests/test_web_dashboard.py"

echo "======================================================================"
echo " [✓] TODOS OS TESTES (FASES 1 A 6) FORAM APROVADOS COM SUCESSO!"
echo "======================================================================"
