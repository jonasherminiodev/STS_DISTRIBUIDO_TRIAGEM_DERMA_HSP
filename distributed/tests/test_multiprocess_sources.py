#!/usr/bin/env python3
"""
Teste de integração de ponta a ponta com as 3 Fontes de Dados e o Gateway (Fase 3).
Valida descoberta das 3 fontes, fluxo contínuo UDP, controle via gRPC e alertas imediatos.
"""
import os
import sys
import time
import unittest
import grpc

WORKSPACE_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
VENV_PACKAGES = os.path.join(WORKSPACE_ROOT, "ANALISE_IMG_CANCER_DE_PELE ", ".venv", "lib", "python3.9", "site-packages")
DISTRIBUTED_DIR = os.path.join(WORKSPACE_ROOT, "distributed")

if os.path.exists(VENV_PACKAGES) and VENV_PACKAGES not in sys.path:
    sys.path.insert(0, VENV_PACKAGES)
if DISTRIBUTED_DIR not in sys.path:
    sys.path.insert(0, DISTRIBUTED_DIR)

from generated import (
    common_pb2,
    device_control_pb2,
    device_control_pb2_grpc,
)
from gateway import GatewayServer
from sources import DermatoscopySource, UvChamberSource, PatchSensorSource


class TestThreeDataSourcesIntegration(unittest.TestCase):

    def setUp(self):
        # Portas isoladas para o teste
        self.multicast_port = 10070
        self.discovery_resp_port = 10071
        self.telemetry_port = 9070
        self.grpc_port_source1 = 50071

        # 1. Inicia o Gateway
        self.gateway = GatewayServer(
            multicast_group="224.1.1.1",
            multicast_port=self.multicast_port,
            discovery_response_port=self.discovery_resp_port,
            udp_telemetry_port=self.telemetry_port,
            offline_timeout_seconds=5.0,
            gateway_id="GATEWAY-INT-TEST",
        )
        self.gateway.start()

        # 2. Inicia Fonte 1: Estação de Dermatoscopia (Controlável gRPC)
        self.source1 = DermatoscopySource(
            device_id="DERMATOSCOPY-01",
            grpc_port=self.grpc_port_source1,
            gateway_host="127.0.0.1",
            gateway_telemetry_port=self.telemetry_port,
            gateway_discovery_resp_port=self.discovery_resp_port,
            sampling_rate_seconds=0.5,
        )
        self.source1.start()

        # 3. Inicia Fonte 2: Sensor de Cabine UV (Não Controlável)
        self.source2 = UvChamberSource(
            device_id="UV-CHAMBER-01",
            gateway_host="127.0.0.1",
            gateway_telemetry_port=self.telemetry_port,
            gateway_discovery_resp_port=self.discovery_resp_port,
            sampling_rate_seconds=0.5,
        )
        self.source2.start()

        # 4. Inicia Fonte 3: Patch Dérmico (Alerta Imediato)
        self.source3 = PatchSensorSource(
            device_id="PATCH-01",
            gateway_host="127.0.0.1",
            gateway_telemetry_port=self.telemetry_port,
            gateway_discovery_resp_port=self.discovery_resp_port,
            sampling_rate_seconds=0.5,
        )
        self.source3.start()

        time.sleep(1.0)

    def tearDown(self):
        self.source1.stop()
        self.source2.stop()
        self.source3.stop()
        self.gateway.stop()
        time.sleep(0.5)

    def test_01_all_three_sources_discovered_and_streaming(self):
        """Verifica se as 3 fontes foram registradas e se estão enviando dados UDP contínuos."""
        # Aguarda algumas iterações de telemetria
        time.sleep(1.5)

        devices = self.gateway.registry.list_devices_proto()
        device_ids = {d.device_id for d in devices}

        self.assertIn("DERMATOSCOPY-01", device_ids)
        self.assertIn("UV-CHAMBER-01", device_ids)
        self.assertIn("PATCH-01", device_ids)
        self.assertEqual(len(device_ids), 3)

        # Inspeciona detalhes individuais
        dev1 = self.gateway.registry.get_device("DERMATOSCOPY-01")
        self.assertEqual(dev1.device_type, common_pb2.DERMATOSCOPY_AI)
        self.assertEqual(dev1.grpc_port, self.grpc_port_source1)
        self.assertGreater(dev1.total_telemetry_count, 0)

        # Verifica se as predições com as 7 classes foram recebidas
        last_t1 = dev1.history[-1][1]
        self.assertEqual(last_t1.WhichOneof("payload"), "dermatoscopy")
        self.assertTrue(len(last_t1.dermatoscopy.latest_prediction.top_class) > 0)
        self.assertEqual(len(last_t1.dermatoscopy.latest_prediction.probabilities), 7)

        dev2 = self.gateway.registry.get_device("UV-CHAMBER-01")
        self.assertEqual(dev2.device_type, common_pb2.UV_CHAMBER)
        self.assertEqual(dev2.grpc_port, 0)
        self.assertGreater(dev2.total_telemetry_count, 0)

        dev3 = self.gateway.registry.get_device("PATCH-01")
        self.assertEqual(dev3.device_type, common_pb2.PATCH_SENSOR)
        self.assertGreater(dev3.total_telemetry_count, 0)

    def test_02_grpc_control_commands_on_source1(self):
        """Testa canal gRPC de controle remoto na Fonte 1 (Dermatoscopia)."""
        channel = grpc.insecure_channel(f"127.0.0.1:{self.grpc_port_source1}")
        try:
            stub = device_control_pb2_grpc.DeviceControlStub(channel)

            # 1. Consulta estado inicial via gRPC
            state_resp = stub.GetDeviceState(device_control_pb2.DeviceStateRequest(device_id="DERMATOSCOPY-01"))
            self.assertEqual(state_resp.state, common_pb2.STATE_ACTIVE)
            self.assertEqual(state_resp.device_type, common_pb2.DERMATOSCOPY_AI)

            # 2. Altera taxa de amostragem
            cfg_resp = stub.ConfigureDevice(
                device_control_pb2.DeviceConfigRequest(
                    target_device_id="DERMATOSCOPY-01",
                    action=device_control_pb2.SET_SAMPLING_RATE,
                    new_sampling_rate_seconds=2.0,
                )
            )
            self.assertTrue(cfg_resp.success)
            self.assertEqual(cfg_resp.effective_sampling_rate, 2.0)
            self.assertEqual(self.source1.sampling_rate_seconds, 2.0)

            # 3. Altera limiar de alerta de malignidade
            cfg_resp2 = stub.ConfigureDevice(
                device_control_pb2.DeviceConfigRequest(
                    target_device_id="DERMATOSCOPY-01",
                    action=device_control_pb2.SET_ALERT_THRESHOLD,
                    new_malignancy_threshold=0.85,
                )
            )
            self.assertTrue(cfg_resp2.success)
            self.assertAlmostEqual(cfg_resp2.effective_threshold, 0.85, places=2)
            self.assertAlmostEqual(self.source1.malignancy_threshold, 0.85, places=2)

            # 4. Simula falha operacional (sensor ótico descalibrado)
            cfg_resp3 = stub.ConfigureDevice(
                device_control_pb2.DeviceConfigRequest(
                    target_device_id="DERMATOSCOPY-01",
                    action=device_control_pb2.SIMULATE_FAULT,
                    fault_simulation_mode="FALHA_CALIBRACAO_OTICA",
                )
            )
            self.assertTrue(cfg_resp3.success)
            self.assertEqual(cfg_resp3.current_state, common_pb2.STATE_ERROR)
            self.assertEqual(self.source1.state, common_pb2.STATE_ERROR)

            # 5. Reseta dispositivo de volta a ativo
            cfg_resp4 = stub.ConfigureDevice(
                device_control_pb2.DeviceConfigRequest(
                    target_device_id="DERMATOSCOPY-01",
                    action=device_control_pb2.RESET,
                )
            )
            self.assertTrue(cfg_resp4.success)
            self.assertEqual(cfg_resp4.current_state, common_pb2.STATE_ACTIVE)
        finally:
            channel.close()

    def test_03_patch_immediate_event_alert(self):
        """Valida que a Fonte 3 dispara pacote UDP de alerta imediato ao detectar hipertermia."""
        dev3 = self.gateway.registry.get_device("PATCH-01")
        initial_alerts = dev3.immediate_alert_count

        # Dispara evento anômalo imediato
        self.source3.trigger_critical_event(
            temperature_celsius=39.9,
            reason="HIPERTERMIA_LOCAL_CRITICA",
        )

        time.sleep(0.3)

        # O Gateway deve ter registrado o alerta imediatamente
        self.assertEqual(dev3.immediate_alert_count, initial_alerts + 1)
        self.assertEqual(dev3.last_fault_reason, "HIPERTERMIA_LOCAL_CRITICA")


if __name__ == "__main__":
    unittest.main(verbosity=2)
