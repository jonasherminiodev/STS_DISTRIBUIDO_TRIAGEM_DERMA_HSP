#!/usr/bin/env python3
"""
Testes de integração com sockets de rede reais para o núcleo do Gateway (Fase 2).
Valida descoberta multicast, receptor UDP unicast e gerenciamento de estado das fontes.
"""
import os
import socket
import sys
import time
import unittest

WORKSPACE_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
VENV_PACKAGES = os.path.join(WORKSPACE_ROOT, "ANALISE_IMG_CANCER_DE_PELE ", ".venv", "lib", "python3.9", "site-packages")
DISTRIBUTED_DIR = os.path.join(WORKSPACE_ROOT, "distributed")

if os.path.exists(VENV_PACKAGES) and VENV_PACKAGES not in sys.path:
    sys.path.insert(0, VENV_PACKAGES)
if DISTRIBUTED_DIR not in sys.path:
    sys.path.insert(0, DISTRIBUTED_DIR)

from generated import common_pb2, discovery_pb2, telemetry_pb2
from gateway import GatewayServer, DeviceRegistry


class TestGatewayCore(unittest.TestCase):

    def setUp(self):
        # Utiliza portas isoladas para evitar conflitos com outros serviços
        self.multicast_port = 10050
        self.discovery_resp_port = 10051
        self.telemetry_port = 9050

        self.gateway = GatewayServer(
            multicast_group="224.1.1.1",
            multicast_port=self.multicast_port,
            discovery_response_port=self.discovery_resp_port,
            udp_telemetry_port=self.telemetry_port,
            offline_timeout_seconds=2.0,  # Timeout curto para testar detecção de falha
            gateway_id="GATEWAY-TEST-01",
        )
        self.gateway.start()
        time.sleep(0.1)

    def tearDown(self):
        self.gateway.stop()
        time.sleep(0.1)

    def test_01_registry_unit_behavior(self):
        """Valida inserção, atualização e expiração na tabela de estado em memória."""
        registry = DeviceRegistry(offline_timeout_seconds=1.0)
        dev = registry.register_or_update(
            device_id="SRC-UNIT-1",
            device_type=common_pb2.UV_CHAMBER,
            ip_address="127.0.0.1",
            grpc_port=0,
            initial_state=common_pb2.STATE_ACTIVE,
        )
        self.assertEqual(dev.device_id, "SRC-UNIT-1")
        self.assertEqual(registry.count(), 1)

        # Simula expiração por inatividade
        dev.last_seen_utc = int(time.time()) - 5
        offline_list = registry.check_timeouts()
        self.assertIn("SRC-UNIT-1", offline_list)
        self.assertEqual(dev.state, common_pb2.STATE_OFFLINE)

    def test_02_real_socket_discovery_reception(self):
        """Valida que o Gateway recebe DiscoveryResponse por socket UDP real e registra a fonte."""
        # Cria socket UDP cliente simulando uma fonte enviando resposta de identificação
        client_sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        try:
            resp = discovery_pb2.DiscoveryResponse(
                device_id="DERM-TEST-01",
                device_type=common_pb2.DERMATOSCOPY_AI,
                ip_address="127.0.0.1",
                grpc_port=50051,
                initial_state=common_pb2.STATE_ACTIVE,
                firmware_version="1.0-alpha",
            )
            data = resp.SerializeToString()
            # Envia diretamente para a porta de resposta do Gateway
            client_sock.sendto(data, ("127.0.0.1", self.discovery_resp_port))

            # Aguarda o socket do Gateway processar
            time.sleep(0.2)

            device = self.gateway.registry.get_device("DERM-TEST-01")
            self.assertIsNotNone(device, "Dispositivo deveria ter sido registrado pelo Gateway")
            self.assertEqual(device.device_type, common_pb2.DERMATOSCOPY_AI)
            self.assertEqual(device.grpc_port, 50051)
            self.assertEqual(device.state, common_pb2.STATE_ACTIVE)
        finally:
            client_sock.close()

    def test_03_real_socket_udp_telemetry_flow(self):
        """Valida fluxo contínuo de dados UDP e alerta imediato de anomalia."""
        client_sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        try:
            # 1. Envia telemetria contínua normal da Fonte 2 (Câmara UV)
            t1 = telemetry_pb2.TelemetryMessage()
            t1.header.device_id = "UV-TEST-02"
            t1.header.device_type = common_pb2.UV_CHAMBER
            t1.header.timestamp_utc = int(time.time())
            t1.header.sequence_number = 1
            t1.is_immediate_alert = False

            t1.uv_chamber.uva_intensity_mw_cm2 = 4.1
            t1.uv_chamber.uvb_intensity_mw_cm2 = 0.5
            t1.uv_chamber.ambient_temperature_celsius = 24.0
            t1.uv_chamber.ambient_humidity_percent = 50.0

            client_sock.sendto(t1.SerializeToString(), ("127.0.0.1", self.telemetry_port))
            time.sleep(0.1)

            dev = self.gateway.registry.get_device("UV-TEST-02")
            self.assertIsNotNone(dev)
            self.assertEqual(dev.total_telemetry_count, 1)
            self.assertEqual(dev.immediate_alert_count, 0)

            # 2. Envia telemetria com ALERTA IMEDIATO da Fonte 3 (Patch Dérmico)
            t2 = telemetry_pb2.TelemetryMessage()
            t2.header.device_id = "PATCH-TEST-03"
            t2.header.device_type = common_pb2.PATCH_SENSOR
            t2.header.timestamp_utc = int(time.time())
            t2.header.sequence_number = 1
            t2.is_immediate_alert = True  # Disparo de anomalia imediato!

            t2.patch_sensor.lesion_temperature_celsius = 39.8
            t2.patch_sensor.tissue_impedance_ohms = 980.0
            t2.patch_sensor.alert_trigger = "HIPERTERMIA_LOCAL_CRITICA"

            client_sock.sendto(t2.SerializeToString(), ("127.0.0.1", self.telemetry_port))
            time.sleep(0.1)

            patch_dev = self.gateway.registry.get_device("PATCH-TEST-03")
            self.assertIsNotNone(patch_dev)
            self.assertEqual(patch_dev.total_telemetry_count, 1)
            self.assertEqual(patch_dev.immediate_alert_count, 1)
            self.assertEqual(patch_dev.last_fault_reason, "HIPERTERMIA_LOCAL_CRITICA")

            # Verifica conversão para Protobuf DeviceInfo
            devices_proto = self.gateway.registry.list_devices_proto()
            self.assertEqual(len(devices_proto), 2)
        finally:
            client_sock.close()

    def test_04_heartbeat_offline_detection(self):
        """Valida que o Gateway detecta fonte desligada e transiciona para OFFLINE."""
        client_sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        try:
            # Envia leitura
            t = telemetry_pb2.TelemetryMessage()
            t.header.device_id = "FAILING-DEV-01"
            t.header.device_type = common_pb2.PATCH_SENSOR
            t.header.timestamp_utc = int(time.time())
            t.header.sequence_number = 1
            t.patch_sensor.lesion_temperature_celsius = 36.5
            client_sock.sendto(t.SerializeToString(), ("127.0.0.1", self.telemetry_port))

            time.sleep(0.2)
            dev = self.gateway.registry.get_device("FAILING-DEV-01")
            self.assertEqual(dev.state, common_pb2.STATE_ACTIVE)

            # Aguarda expiração do timeout configurado (2.0s) + ciclo do monitor
            time.sleep(2.5)

            # Dispositivo deve ter sido transicionado para STATE_OFFLINE
            self.assertEqual(dev.state, common_pb2.STATE_OFFLINE)
        finally:
            client_sock.close()


if __name__ == "__main__":
    unittest.main(verbosity=2)
