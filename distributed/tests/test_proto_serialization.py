#!/usr/bin/env python3
"""
Testes unitários de validação empírica para os contratos Protocol Buffers (.proto).
Verifica instanciação, serialização em bytes binários e integridade de desserialização.
"""
import sys
import os
import unittest
import time

# Configura paths para carregar dependências da workspace e módulos gerados
WORKSPACE_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
VENV_PACKAGES = os.path.join(WORKSPACE_ROOT, "ANALISE_IMG_CANCER_DE_PELE ", ".venv", "lib", "python3.9", "site-packages")
DISTRIBUTED_DIR = os.path.join(WORKSPACE_ROOT, "distributed")

if os.path.exists(VENV_PACKAGES) and VENV_PACKAGES not in sys.path:
    sys.path.insert(0, VENV_PACKAGES)
if DISTRIBUTED_DIR not in sys.path:
    sys.path.insert(0, DISTRIBUTED_DIR)

from generated import (
    common_pb2,
    discovery_pb2,
    telemetry_pb2,
    device_control_pb2,
    device_control_pb2_grpc,
    client_gateway_pb2,
)

# Classes originais do projeto existentes em app.py
ORIGINAL_CANCER_CLASSES = {
    0: "Queratoses actínicas (Pré-cancerosas)",
    1: "Carcinoma de células basais (Maligno)",
    2: "Dermatofibroma (Benigno)",
    3: "Lesões benignas semelhantes a queratose (Benigno)",
    4: "Melanoma (Maligno)",
    5: "Nevos melanocíticos (Benigno)",
    6: "Lesões Vasculares (Benigno)",
}


class TestProtoSerialization(unittest.TestCase):

    def test_01_common_header_serialization(self):
        """Valida MessageHeader e Enums de estado"""
        header = common_pb2.MessageHeader(
            device_id="DERM-01",
            device_type=common_pb2.DERMATOSCOPY_AI,
            timestamp_utc=int(time.time()),
            sequence_number=42,
        )
        data = header.SerializeToString()
        self.assertIsInstance(data, bytes)
        self.assertGreater(len(data), 0)

        deserialized = common_pb2.MessageHeader()
        deserialized.ParseFromString(data)
        self.assertEqual(deserialized.device_id, "DERM-01")
        self.assertEqual(deserialized.device_type, common_pb2.DERMATOSCOPY_AI)
        self.assertEqual(deserialized.sequence_number, 42)

    def test_02_discovery_protocol(self):
        """Valida mensagens de Descoberta UDP Multicast"""
        req = discovery_pb2.DiscoveryRequest(
            gateway_id="GATEWAY-CENTRAL-01",
            timestamp_utc=int(time.time()),
        )
        req_bytes = req.SerializeToString()
        deser_req = discovery_pb2.DiscoveryRequest()
        deser_req.ParseFromString(req_bytes)
        self.assertEqual(deser_req.gateway_id, "GATEWAY-CENTRAL-01")

        resp = discovery_pb2.DiscoveryResponse(
            device_id="DERM-01",
            device_type=common_pb2.DERMATOSCOPY_AI,
            ip_address="127.0.0.1",
            grpc_port=50051,
            initial_state=common_pb2.STATE_ACTIVE,
            firmware_version="v1.0.0-ia",
        )
        resp_bytes = resp.SerializeToString()
        deser_resp = discovery_pb2.DiscoveryResponse()
        deser_resp.ParseFromString(resp_bytes)
        self.assertEqual(deser_resp.device_id, "DERM-01")
        self.assertEqual(deser_resp.grpc_port, 50051)
        self.assertEqual(deser_resp.initial_state, common_pb2.STATE_ACTIVE)

    def test_03_telemetry_source_1_dermatoscopy_ia(self):
        """Valida Telemetria da Fonte 1 com as 7 classes reais de lesões dermatológicas"""
        telemetry = telemetry_pb2.TelemetryMessage()
        telemetry.header.device_id = "DERM-01"
        telemetry.header.device_type = common_pb2.DERMATOSCOPY_AI
        telemetry.header.timestamp_utc = int(time.time())
        telemetry.header.sequence_number = 1
        telemetry.is_immediate_alert = False

        payload = telemetry.dermatoscopy
        payload.sensor_temperature_celsius = 34.5
        payload.led_intensity_lux = 850.0
        payload.battery_percent = 92.5
        payload.total_examinations = 15

        pred = payload.latest_prediction
        pred.top_class = ORIGINAL_CANCER_CLASSES[4]  # Melanoma (Maligno)
        pred.top_probability = 0.875
        pred.is_malignant = True
        pred.image_reference = "lesion_patient_102.jpg"

        # Popula as 7 classes
        sample_probs = [0.01, 0.05, 0.02, 0.01, 0.875, 0.03, 0.005]
        for idx, prob in enumerate(sample_probs):
            item = pred.probabilities.add()
            item.class_id = idx
            item.class_name = ORIGINAL_CANCER_CLASSES[idx]
            item.probability = prob

        data = telemetry.SerializeToString()
        self.assertGreater(len(data), 0)

        deser = telemetry_pb2.TelemetryMessage()
        deser.ParseFromString(data)
        self.assertEqual(deser.header.device_id, "DERM-01")
        self.assertFalse(deser.is_immediate_alert)
        self.assertEqual(deser.WhichOneof("payload"), "dermatoscopy")
        self.assertEqual(deser.dermatoscopy.latest_prediction.top_class, "Melanoma (Maligno)")
        self.assertEqual(len(deser.dermatoscopy.latest_prediction.probabilities), 7)
        self.assertTrue(deser.dermatoscopy.latest_prediction.is_malignant)

    def test_04_telemetry_source_2_uv_chamber(self):
        """Valida Telemetria contínua da Fonte 2 (Câmara UV / Fototerapia)"""
        telemetry = telemetry_pb2.TelemetryMessage()
        telemetry.header.device_id = "UV-CHAMBER-01"
        telemetry.header.device_type = common_pb2.UV_CHAMBER
        telemetry.header.timestamp_utc = int(time.time())
        telemetry.header.sequence_number = 10
        telemetry.is_immediate_alert = False

        payload = telemetry.uv_chamber
        payload.uva_intensity_mw_cm2 = 3.25
        payload.uvb_intensity_mw_cm2 = 0.45
        payload.ambient_temperature_celsius = 22.8
        payload.ambient_humidity_percent = 48.0
        payload.safety_door_closed = True

        data = telemetry.SerializeToString()
        deser = telemetry_pb2.TelemetryMessage()
        deser.ParseFromString(data)
        self.assertEqual(deser.WhichOneof("payload"), "uv_chamber")
        self.assertAlmostEqual(deser.uv_chamber.uva_intensity_mw_cm2, 3.25, places=2)
        self.assertTrue(deser.uv_chamber.safety_door_closed)

    def test_05_telemetry_source_3_patch_immediate_alert(self):
        """Valida Telemetria da Fonte 3 em disparo IMEDIATO por alarme de hipertermia"""
        telemetry = telemetry_pb2.TelemetryMessage()
        telemetry.header.device_id = "PATCH-01"
        telemetry.header.device_type = common_pb2.PATCH_SENSOR
        telemetry.header.timestamp_utc = int(time.time())
        telemetry.header.sequence_number = 99
        telemetry.is_immediate_alert = True  # ENVIO IMEDIATO

        payload = telemetry.patch_sensor
        payload.lesion_temperature_celsius = 39.4  # Hipertermia crítica
        payload.tissue_impedance_ohms = 1250.0
        payload.hydration_percent = 18.5
        payload.alert_trigger = "HIPERTERMIA_LOCAL_CRITICA"

        data = telemetry.SerializeToString()
        deser = telemetry_pb2.TelemetryMessage()
        deser.ParseFromString(data)
        self.assertTrue(deser.is_immediate_alert)
        self.assertEqual(deser.WhichOneof("payload"), "patch_sensor")
        self.assertEqual(deser.patch_sensor.alert_trigger, "HIPERTERMIA_LOCAL_CRITICA")
        self.assertAlmostEqual(deser.patch_sensor.lesion_temperature_celsius, 39.4, places=1)

    def test_06_grpc_device_control_messages(self):
        """Valida mensagens de controle e estado do serviço gRPC"""
        cfg_req = device_control_pb2.DeviceConfigRequest(
            target_device_id="DERM-01",
            action=device_control_pb2.SET_SAMPLING_RATE,
            new_sampling_rate_seconds=5.0,
            new_malignancy_threshold=0.70,
        )
        data = cfg_req.SerializeToString()
        deser_req = device_control_pb2.DeviceConfigRequest()
        deser_req.ParseFromString(data)
        self.assertEqual(deser_req.target_device_id, "DERM-01")
        self.assertEqual(deser_req.new_sampling_rate_seconds, 5.0)

        cfg_resp = device_control_pb2.DeviceConfigResponse(
            success=True,
            message="Taxa de amostragem alterada para 5.0s com sucesso",
            current_state=common_pb2.STATE_ACTIVE,
            effective_sampling_rate=5.0,
            effective_threshold=0.70,
        )
        resp_data = cfg_resp.SerializeToString()
        deser_resp = device_control_pb2.DeviceConfigResponse()
        deser_resp.ParseFromString(resp_data)
        self.assertTrue(deser_resp.success)
        self.assertEqual(deser_resp.current_state, common_pb2.STATE_ACTIVE)

    def test_07_client_gateway_tcp_messages_and_3_queries(self):
        """Valida mensagens Cliente-Gateway TCP e as 3 consultas analíticas"""
        # Teste Consulta 1: Malignidade
        req1 = client_gateway_pb2.ClientRequest(
            request_id="REQ-001",
            command=client_gateway_pb2.CMD_ANALYTICS_QUERY,
        )
        req1.analytics_query.query_type = client_gateway_pb2.QUERY_1_MALIGNANCY_SUMMARY
        req1.analytics_query.time_window_seconds = 3600

        data1 = req1.SerializeToString()
        deser_req1 = client_gateway_pb2.ClientRequest()
        deser_req1.ParseFromString(data1)
        self.assertEqual(deser_req1.analytics_query.query_type, client_gateway_pb2.QUERY_1_MALIGNANCY_SUMMARY)

        # Resposta da Consulta 1
        resp1 = client_gateway_pb2.GatewayResponse(
            request_id="REQ-001",
            status=client_gateway_pb2.STATUS_OK,
            message="Relatório de triagem oncológica calculado com sucesso",
        )
        resp1.analytics.query_type = client_gateway_pb2.QUERY_1_MALIGNANCY_SUMMARY
        resp1.analytics.time_window_seconds = 3600
        mal_res = resp1.analytics.malignancy
        mal_res.total_screenings = 50
        mal_res.malignant_count = 12
        mal_res.malignancy_rate = 0.24
        mal_res.avg_confidence = 0.88
        mal_res.class_distribution["Melanoma (Maligno)"] = 8
        mal_res.class_distribution["Carcinoma de células basais (Maligno)"] = 4

        data_resp1 = resp1.SerializeToString()
        deser_resp1 = client_gateway_pb2.GatewayResponse()
        deser_resp1.ParseFromString(data_resp1)
        self.assertEqual(deser_resp1.status, client_gateway_pb2.STATUS_OK)
        self.assertEqual(deser_resp1.analytics.malignancy.malignant_count, 12)
        self.assertEqual(deser_resp1.analytics.malignancy.class_distribution["Melanoma (Maligno)"], 8)

        # Teste Consulta 2: UV e Clima
        resp2 = client_gateway_pb2.GatewayResponse(
            request_id="REQ-002",
            status=client_gateway_pb2.STATUS_OK,
        )
        resp2.analytics.query_type = client_gateway_pb2.QUERY_2_UV_CLIMATE_SUMMARY
        uv_res = resp2.analytics.uv_climate
        uv_res.total_samples = 120
        uv_res.avg_uva = 3.10
        uv_res.std_dev_uva = 0.15
        uv_res.avg_temperature = 23.5
        uv_res.std_dev_temperature = 0.8
        data_resp2 = resp2.SerializeToString()
        deser_resp2 = client_gateway_pb2.GatewayResponse()
        deser_resp2.ParseFromString(data_resp2)
        self.assertEqual(deser_resp2.analytics.uv_climate.total_samples, 120)

        # Teste Consulta 3: Ranking de Incidentes
        resp3 = client_gateway_pb2.GatewayResponse(
            request_id="REQ-003",
            status=client_gateway_pb2.STATUS_OK,
        )
        resp3.analytics.query_type = client_gateway_pb2.QUERY_3_DEVICE_INCIDENTS_SUMMARY
        inc_res = resp3.analytics.incidents
        inc_res.most_unstable_device_id = "PATCH-01"
        item = inc_res.devices_ranked.add()
        item.device_id = "PATCH-01"
        item.device_type = common_pb2.PATCH_SENSOR
        item.immediate_alert_count = 5
        item.last_incident_description = "HIPERTERMIA_LOCAL_CRITICA"

        data_resp3 = resp3.SerializeToString()
        deser_resp3 = client_gateway_pb2.GatewayResponse()
        deser_resp3.ParseFromString(data_resp3)
        self.assertEqual(deser_resp3.analytics.incidents.most_unstable_device_id, "PATCH-01")
        self.assertEqual(len(deser_resp3.analytics.incidents.devices_ranked), 1)


if __name__ == "__main__":
    unittest.main(verbosity=2)
