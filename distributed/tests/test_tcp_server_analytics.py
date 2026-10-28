#!/usr/bin/env python3
"""
Testes de integração do Servidor TCP, Despacho gRPC e Consultas Analíticas (Fase 4).
Valida comunicação Cliente-Gateway via TCP com Length-Prefixed Framing e Protocol Buffers.
"""
import os
import socket
import struct
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

from generated import common_pb2, device_control_pb2, client_gateway_pb2
from gateway import GatewayServer, recv_exact, send_length_prefixed
from sources import DermatoscopySource, UvChamberSource, PatchSensorSource


def send_tcp_request(host: str, port: int, request: client_gateway_pb2.ClientRequest) -> client_gateway_pb2.GatewayResponse:
    """Envia requisição Protobuf via socket TCP usando enquadramento de tamanho."""
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.settimeout(5.0)
    try:
        sock.connect((host, port))
        req_bytes = request.SerializeToString()
        send_length_prefixed(sock, req_bytes)

        prefix = recv_exact(sock, 4)
        if not prefix:
            raise ConnectionError("Conexão fechada pelo Gateway sem dados de resposta")

        resp_len = struct.unpack(">I", prefix)[0]
        resp_payload = recv_exact(sock, resp_len)
        if not resp_payload:
            raise ConnectionError("Payload incompleto recebido do Gateway")

        response = client_gateway_pb2.GatewayResponse()
        response.ParseFromString(resp_payload)
        return response
    finally:
        sock.close()


class TestTCPServerAndAnalytics(unittest.TestCase):

    def setUp(self):
        self.tmp_dir = tempfile.mkdtemp()
        self.db_path = os.path.join(self.tmp_dir, "test_telemetry.db")

        self.tcp_port = 8080
        self.multicast_port = 10080
        self.discovery_resp_port = 10081
        self.telemetry_port = 9080
        self.grpc_port_derm = 50081

        # 1. Inicia Gateway
        self.gateway = GatewayServer(
            tcp_port=self.tcp_port,
            multicast_group="224.1.1.1",
            multicast_port=self.multicast_port,
            discovery_response_port=self.discovery_resp_port,
            udp_telemetry_port=self.telemetry_port,
            db_path=self.db_path,
        )
        self.gateway.start()

        # 2. Inicia Fonte 1 (Dermatoscopia)
        self.source1 = DermatoscopySource(
            device_id="DERM-TCP-01",
            grpc_port=self.grpc_port_derm,
            gateway_host="127.0.0.1",
            gateway_telemetry_port=self.telemetry_port,
            gateway_discovery_resp_port=self.discovery_resp_port,
            sampling_rate_seconds=0.3,
        )
        self.source1.start()

        # 3. Inicia Fonte 2 (Câmara UV)
        self.source2 = UvChamberSource(
            device_id="UV-TCP-02",
            gateway_host="127.0.0.1",
            gateway_telemetry_port=self.telemetry_port,
            gateway_discovery_resp_port=self.discovery_resp_port,
            sampling_rate_seconds=0.3,
        )
        self.source2.start()

        # 4. Inicia Fonte 3 (Patch Dérmico)
        self.source3 = PatchSensorSource(
            device_id="PATCH-TCP-03",
            gateway_host="127.0.0.1",
            gateway_telemetry_port=self.telemetry_port,
            gateway_discovery_resp_port=self.discovery_resp_port,
            sampling_rate_seconds=0.3,
        )
        self.source3.start()

        time.sleep(1.0)

    def tearDown(self):
        self.source1.stop()
        self.source2.stop()
        self.source3.stop()
        self.gateway.stop()
        time.sleep(0.3)

    def test_01_tcp_list_devices(self):
        """Valida consulta de listagem de fontes via socket TCP."""
        req = client_gateway_pb2.ClientRequest(
            request_id="REQ-LIST-01",
            command=client_gateway_pb2.CMD_LIST_DEVICES,
        )
        resp = send_tcp_request("127.0.0.1", self.tcp_port, req)

        self.assertEqual(resp.request_id, "REQ-LIST-01")
        self.assertEqual(resp.status, client_gateway_pb2.STATUS_OK)
        self.assertGreaterEqual(len(resp.devices), 3)

        dev_ids = [d.device_id for d in resp.devices]
        self.assertIn("DERM-TCP-01", dev_ids)
        self.assertIn("UV-TCP-02", dev_ids)
        self.assertIn("PATCH-TCP-03", dev_ids)

    def test_02_tcp_to_grpc_device_control(self):
        """Valida cadeia TCP (Cliente -> Gateway) e gRPC (Gateway -> Fonte 1)."""
        # Cliente pede ao Gateway via TCP para alterar parâmetros da Fonte 1
        req = client_gateway_pb2.ClientRequest(
            request_id="REQ-CTRL-02",
            command=client_gateway_pb2.CMD_SEND_DEVICE_CONTROL,
            target_device_id="DERM-TCP-01",
            device_config=device_control_pb2.DeviceConfigRequest(
                target_device_id="DERM-TCP-01",
                action=device_control_pb2.SET_SAMPLING_RATE,
                new_sampling_rate_seconds=1.5,
            ),
        )
        resp = send_tcp_request("127.0.0.1", self.tcp_port, req)

        self.assertEqual(resp.status, client_gateway_pb2.STATUS_OK)
        self.assertTrue(resp.config_response.success)
        self.assertEqual(resp.config_response.effective_sampling_rate, 1.5)
        self.assertEqual(self.source1.sampling_rate_seconds, 1.5)

    def test_03_three_aggregated_analytics_queries(self):
        """Valida execução das 3 consultas analíticas agregadas exigidas via TCP."""
        # Aguarda algumas coletas de telemetria
        time.sleep(1.5)

        # Dispara um alerta imediato na Fonte 3 para ter dados no ranking de incidentes
        self.source3.trigger_critical_event(39.8, "HIPERTERMIA_LOCAL_CRITICA")
        time.sleep(0.3)

        # --- Consulta 1: Resumo de Malignidade IA ---
        req1 = client_gateway_pb2.ClientRequest(
            request_id="REQ-ANALYTICS-1",
            command=client_gateway_pb2.CMD_ANALYTICS_QUERY,
            analytics_query=client_gateway_pb2.AnalyticsQueryRequest(
                query_type=client_gateway_pb2.QUERY_1_MALIGNANCY_SUMMARY,
                time_window_seconds=3600,
            ),
        )
        resp1 = send_tcp_request("127.0.0.1", self.tcp_port, req1)
        self.assertEqual(resp1.status, client_gateway_pb2.STATUS_OK)
        mal = resp1.analytics.malignancy
        self.assertGreater(mal.total_screenings, 0)
        self.assertGreater(mal.avg_confidence, 0.0)
        self.assertGreaterEqual(mal.malignancy_rate, 0.0)
        self.assertGreater(len(mal.class_distribution), 0)

        # --- Consulta 2: Resumo de Radiação UV e Clima ---
        req2 = client_gateway_pb2.ClientRequest(
            request_id="REQ-ANALYTICS-2",
            command=client_gateway_pb2.CMD_ANALYTICS_QUERY,
            analytics_query=client_gateway_pb2.AnalyticsQueryRequest(
                query_type=client_gateway_pb2.QUERY_2_UV_CLIMATE_SUMMARY,
                time_window_seconds=3600,
            ),
        )
        resp2 = send_tcp_request("127.0.0.1", self.tcp_port, req2)
        self.assertEqual(resp2.status, client_gateway_pb2.STATUS_OK)
        uv = resp2.analytics.uv_climate
        self.assertGreater(uv.total_samples, 0)
        self.assertGreater(uv.avg_uva, 2.0)
        self.assertGreater(uv.avg_temperature, 15.0)

        # --- Consulta 3: Ranking de Incidentes ---
        req3 = client_gateway_pb2.ClientRequest(
            request_id="REQ-ANALYTICS-3",
            command=client_gateway_pb2.CMD_ANALYTICS_QUERY,
            analytics_query=client_gateway_pb2.AnalyticsQueryRequest(
                query_type=client_gateway_pb2.QUERY_3_DEVICE_INCIDENTS_SUMMARY,
                time_window_seconds=3600,
            ),
        )
        resp3 = send_tcp_request("127.0.0.1", self.tcp_port, req3)
        self.assertEqual(resp3.status, client_gateway_pb2.STATUS_OK)
        inc = resp3.analytics.incidents
        self.assertEqual(inc.most_unstable_device_id, "PATCH-TCP-03")
        self.assertGreaterEqual(len(inc.devices_ranked), 1)

    def test_04_sqlite_persistence_bonus(self):
        """Valida que o Gateway persistiu as leituras recebidas em SQLite."""
        time.sleep(1.0)
        saved_count = self.gateway.storage.get_recent_count()
        self.assertGreater(saved_count, 0, "Deveria haver leituras gravadas no SQLite")


if __name__ == "__main__":
    unittest.main(verbosity=2)
