#!/usr/bin/env python3
"""
Teste automatizado de ponta a ponta do Cliente CLI (Fase 5).
Executa o cli_client.py como subprocesso real do sistema operacional e valida saídas e códigos de retorno.
"""
import os
import subprocess
import sys
import tempfile
import time
import unittest

WORKSPACE_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
VENV_PACKAGES = os.path.join(WORKSPACE_ROOT, "ANALISE_IMG_CANCER_DE_PELE ", ".venv", "lib", "python3.9", "site-packages")
DISTRIBUTED_DIR = os.path.join(WORKSPACE_ROOT, "distributed")

if os.path.exists(VENV_PACKAGES) and VENV_PACKAGES not in sys.path:
    sys.path.insert(0, VENV_PACKAGES)
if DISTRIBUTED_DIR not in sys.path:
    sys.path.insert(0, DISTRIBUTED_DIR)

from gateway import GatewayServer
from sources import DermatoscopySource, UvChamberSource, PatchSensorSource


class TestCLIClientEndToEnd(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.tmp_dir = tempfile.mkdtemp()
        cls.db_path = os.path.join(cls.tmp_dir, "test_cli_telemetry.db")

        cls.tcp_port = 8090
        cls.multicast_port = 10090
        cls.discovery_resp_port = 10091
        cls.telemetry_port = 9090
        cls.grpc_port_derm = 50091

        # 1. Inicia Gateway
        cls.gateway = GatewayServer(
            tcp_port=cls.tcp_port,
            multicast_group="224.1.1.1",
            multicast_port=cls.multicast_port,
            discovery_response_port=cls.discovery_resp_port,
            udp_telemetry_port=cls.telemetry_port,
            db_path=cls.db_path,
        )
        cls.gateway.start()

        # 2. Inicia as 3 fontes
        cls.source1 = DermatoscopySource(
            device_id="DERM-CLI-01",
            grpc_port=cls.grpc_port_derm,
            gateway_host="127.0.0.1",
            gateway_telemetry_port=cls.telemetry_port,
            gateway_discovery_resp_port=cls.discovery_resp_port,
            sampling_rate_seconds=0.3,
        )
        cls.source1.start()

        cls.source2 = UvChamberSource(
            device_id="UV-CLI-02",
            gateway_host="127.0.0.1",
            gateway_telemetry_port=cls.telemetry_port,
            gateway_discovery_resp_port=cls.discovery_resp_port,
            sampling_rate_seconds=0.3,
        )
        cls.source2.start()

        cls.source3 = PatchSensorSource(
            device_id="PATCH-CLI-03",
            gateway_host="127.0.0.1",
            gateway_telemetry_port=cls.telemetry_port,
            gateway_discovery_resp_port=cls.discovery_resp_port,
            sampling_rate_seconds=0.3,
        )
        cls.source3.start()

        time.sleep(1.5)

    @classmethod
    def tearDownClass(cls):
        cls.source1.stop()
        cls.source2.stop()
        cls.source3.stop()
        cls.gateway.stop()
        time.sleep(0.3)

    def _run_cli(self, extra_args):
        cli_script = os.path.join(DISTRIBUTED_DIR, "client", "cli_client.py")
        cmd = [
            sys.executable,
            cli_script,
            "--port", str(self.tcp_port),
        ] + extra_args

        result = subprocess.run(cmd, capture_output=True, text=True)
        return result

    def test_01_cli_list_devices(self):
        """Valida execução de 'cli_client.py --list'."""
        res = self._run_cli(["--list"])
        self.assertEqual(res.returncode, 0, f"Erro: {res.stderr}")
        self.assertIn("DERM-CLI-01", res.stdout)
        self.assertIn("UV-CLI-02", res.stdout)
        self.assertIn("PATCH-CLI-03", res.stdout)
        self.assertIn("Dermatoscópio com IA", res.stdout)

    def test_02_cli_control_command(self):
        """Valida envio de comandos gRPC via CLI."""
        # 1. Altera taxa de amostragem
        res = self._run_cli(["--control-device", "DERM-CLI-01", "--action", "SET_SAMPLING_RATE", "--rate", "1.8"])
        self.assertEqual(res.returncode, 0, f"Erro: {res.stderr}")
        self.assertIn("Taxa de amostragem alterada para 1.8s", res.stdout)
        self.assertEqual(self.source1.sampling_rate_seconds, 1.8)

        # 2. Simula falha
        res2 = self._run_cli(["--control-device", "DERM-CLI-01", "--action", "SIMULATE_FAULT"])
        self.assertEqual(res2.returncode, 0)
        self.assertIn("ERRO / FALHA", res2.stdout)

        # 3. Reseta fonte
        res3 = self._run_cli(["--control-device", "DERM-CLI-01", "--action", "RESET"])
        self.assertEqual(res3.returncode, 0)
        self.assertIn("ATIVO (OK)", res3.stdout)

    def test_03_cli_three_queries(self):
        """Valida execução das 3 consultas analíticas agregadas via CLI."""
        # Dispara alerta imediato na Fonte 3 para enriquecer a consulta 3
        self.source3.trigger_critical_event(39.7, "HIPERTERMIA_LOCAL_CRITICA")
        time.sleep(0.3)

        # Consulta 1: IA Malignidade
        res1 = self._run_cli(["--query", "1"])
        self.assertEqual(res1.returncode, 0, f"Erro: {res1.stderr}")
        self.assertIn("CONSULTA ANALÍTICA 1: RESUMO DE TRIAGEM ONCOLÓGICA", res1.stdout)
        self.assertIn("Total de exames dermatológicos avaliados:", res1.stdout)
        self.assertIn("Taxa de detecção de malignidade:", res1.stdout)

        # Consulta 2: UV e Clima
        res2 = self._run_cli(["--query", "2"])
        self.assertEqual(res2.returncode, 0, f"Erro: {res2.stderr}")
        self.assertIn("CONSULTA ANALÍTICA 2: DOSIMETRIA UV E CLIMA DE SALA", res2.stdout)
        self.assertIn("Intensidade UVA média", res2.stdout)
        self.assertIn("Temperatura ambiente média", res2.stdout)

        # Consulta 3: Ranking de Incidentes
        res3 = self._run_cli(["--query", "3"])
        self.assertEqual(res3.returncode, 0, f"Erro: {res3.stderr}")
        self.assertIn("CONSULTA ANALÍTICA 3: RANKING DE INCIDENTES E INSTABILIDADES", res3.stdout)
        self.assertIn("PATCH-CLI-03", res3.stdout)


if __name__ == "__main__":
    unittest.main(verbosity=2)
