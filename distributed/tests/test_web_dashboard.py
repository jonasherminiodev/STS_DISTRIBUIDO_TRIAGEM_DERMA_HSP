#!/usr/bin/env python3
"""
Testes de integração do Cliente com Interface Gráfica Web (Fase 6 Bônus).
Valida rotas HTTP do Flask, renderização do dashboard e comunicação via TCP com o Gateway.
"""
import json
import os
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
from web_client import web_app
from client.tcp_gateway_client import TCPGatewayClient


class TestWebDashboard(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.tmp_dir = tempfile.mkdtemp()
        cls.db_path = os.path.join(cls.tmp_dir, "test_web_telemetry.db")

        cls.tcp_port = 8100
        cls.multicast_port = 10100
        cls.discovery_resp_port = 10101
        cls.telemetry_port = 9100
        cls.grpc_port_derm = 50101

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
            device_id="DERM-WEB-01",
            grpc_port=cls.grpc_port_derm,
            gateway_host="127.0.0.1",
            gateway_telemetry_port=cls.telemetry_port,
            gateway_discovery_resp_port=cls.discovery_resp_port,
            sampling_rate_seconds=0.3,
        )
        cls.source1.start()

        cls.source2 = UvChamberSource(
            device_id="UV-WEB-02",
            gateway_host="127.0.0.1",
            gateway_telemetry_port=cls.telemetry_port,
            gateway_discovery_resp_port=cls.discovery_resp_port,
            sampling_rate_seconds=0.3,
        )
        cls.source2.start()

        cls.source3 = PatchSensorSource(
            device_id="PATCH-WEB-03",
            gateway_host="127.0.0.1",
            gateway_telemetry_port=cls.telemetry_port,
            gateway_discovery_resp_port=cls.discovery_resp_port,
            sampling_rate_seconds=0.3,
        )
        cls.source3.start()

        # Configura o cliente TCP da aplicação Web para apontar para a porta do teste
        web_app.gateway_client = TCPGatewayClient(host="127.0.0.1", port=cls.tcp_port)
        cls.client = web_app.app.test_client()

        time.sleep(1.5)

    @classmethod
    def tearDownClass(cls):
        cls.source1.stop()
        cls.source2.stop()
        cls.source3.stop()
        cls.gateway.stop()
        time.sleep(0.3)

    def test_01_index_html_route(self):
        """Valida que a rota principal renderiza a página do Dashboard."""
        response = self.client.get("/")
        self.assertEqual(response.status_code, 200)
        content = response.get_data(as_text=True)
        self.assertIn("Sistema Distribuído de Gestão Inteligente para Triagem Dermatológica", content)
        self.assertIn("chart.js", content.lower())
        self.assertIn("uvChart", content)
        self.assertIn("cancerChart", content)

    def test_02_api_devices_route(self):
        """Valida endpoint /api/devices retornando lista de fontes via TCP."""
        response = self.client.get("/api/devices")
        self.assertEqual(response.status_code, 200)
        data = json.loads(response.get_data(as_text=True))
        self.assertTrue(data.get("success"))
        devices = data.get("devices", [])
        self.assertGreaterEqual(len(devices), 3)

        dev_ids = [d["device_id"] for d in devices]
        self.assertIn("DERM-WEB-01", dev_ids)
        self.assertIn("UV-WEB-02", dev_ids)
        self.assertIn("PATCH-WEB-03", dev_ids)

    def test_03_api_control_route(self):
        """Valida endpoint /api/control disparando comando gRPC através do Gateway."""
        payload = {
            "device_id": "DERM-WEB-01",
            "action": "SET_SAMPLING_RATE",
            "sampling_rate": 2.2,
        }
        response = self.client.post(
            "/api/control",
            data=json.dumps(payload),
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 200)
        data = json.loads(response.get_data(as_text=True))
        self.assertTrue(data.get("success"))
        self.assertIn("2.2s", data.get("message", ""))
        self.assertEqual(self.source1.sampling_rate_seconds, 2.2)

    def test_04_api_analytics_routes(self):
        """Valida endpoints /api/analytics/1, /2 e /3 retornando métricas agregadas."""
        # 1. Consulta 1: Malignidade
        r1 = self.client.get("/api/analytics/1")
        self.assertEqual(r1.status_code, 200)
        d1 = json.loads(r1.get_data(as_text=True))
        self.assertTrue(d1.get("success"))
        self.assertIn("malignancy", d1)
        self.assertGreater(d1["malignancy"]["total_screenings"], 0)

        # 2. Consulta 2: UV e Clima
        r2 = self.client.get("/api/analytics/2")
        self.assertEqual(r2.status_code, 200)
        d2 = json.loads(r2.get_data(as_text=True))
        self.assertTrue(d2.get("success"))
        self.assertIn("uv_climate", d2)
        self.assertGreater(d2["uv_climate"]["total_samples"], 0)

        # 3. Consulta 3: Incidentes
        r3 = self.client.get("/api/analytics/3")
        self.assertEqual(r3.status_code, 200)
        d3 = json.loads(r3.get_data(as_text=True))
        self.assertTrue(d3.get("success"))
        self.assertIn("incidents", d3)


if __name__ == "__main__":
    unittest.main(verbosity=2)
