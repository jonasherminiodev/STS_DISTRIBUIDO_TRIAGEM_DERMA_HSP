"""
Motor de Consultas Analíticas Agregadas do Gateway.
Processa o histórico de telemetria das fontes para responder às 3 consultas exigidas pela especificação.
"""
import math
import time
from typing import List, Tuple
from collections import Counter

from generated import common_pb2, client_gateway_pb2, telemetry_pb2
from .device_registry import DeviceRegistry


class AnalyticsEngine:
    """Calcula métricas estatísticas e agregações temporais sobre os dados de telemetria."""

    def __init__(self, registry: DeviceRegistry):
        self.registry = registry

    def compute_query(
        self,
        query_type: client_gateway_pb2.AnalyticsType,
        time_window_seconds: int = 3600,
    ) -> client_gateway_pb2.AnalyticsResponse:
        """Executa a agregação solicitada respeitando a janela temporal."""
        now = time.time()
        min_time = (now - time_window_seconds) if time_window_seconds > 0 else 0

        resp = client_gateway_pb2.AnalyticsResponse(
            query_type=query_type,
            time_window_seconds=time_window_seconds,
        )

        if query_type == client_gateway_pb2.QUERY_1_MALIGNANCY_SUMMARY:
            resp.malignancy.CopyFrom(self._compute_malignancy_summary(min_time))
        elif query_type == client_gateway_pb2.QUERY_2_UV_CLIMATE_SUMMARY:
            resp.uv_climate.CopyFrom(self._compute_uv_climate_summary(min_time))
        elif query_type == client_gateway_pb2.QUERY_3_DEVICE_INCIDENTS_SUMMARY:
            resp.incidents.CopyFrom(self._compute_device_incidents_summary())

        return resp

    def _compute_malignancy_summary(self, min_timestamp: float) -> client_gateway_pb2.MalignancyAnalyticsResult:
        """Consulta 1: Taxa de malignidade, média de confiança e distribuição das 7 classes de IA."""
        total = 0
        malignant = 0
        confidences: List[float] = []
        classes_counter: Counter = Counter()

        with self.registry._lock:
            for dev in self.registry._devices.values():
                if dev.device_type == common_pb2.DERMATOSCOPY_AI:
                    for ts, tmsg in dev.history:
                        if ts >= min_timestamp and tmsg.WhichOneof("payload") == "dermatoscopy":
                            pred = tmsg.dermatoscopy.latest_prediction
                            if pred.top_class:
                                total += 1
                                if pred.is_malignant:
                                    malignant += 1
                                confidences.append(pred.top_probability)
                                classes_counter[pred.top_class] += 1

        rate = (malignant / total) if total > 0 else 0.0
        avg_conf = (sum(confidences) / len(confidences)) if confidences else 0.0

        res = client_gateway_pb2.MalignancyAnalyticsResult(
            total_screenings=total,
            malignant_count=malignant,
            malignancy_rate=round(rate, 4),
            avg_confidence=round(avg_conf, 4),
        )
        for cname, count in classes_counter.items():
            res.class_distribution[cname] = count

        return res

    def _compute_uv_climate_summary(self, min_timestamp: float) -> client_gateway_pb2.UvClimateAnalyticsResult:
        """Consulta 2: Média e desvio padrão de radiação UV, temperatura e umidade da sala."""
        uvas: List[float] = []
        uvbs: List[float] = []
        temps: List[float] = []
        humids: List[float] = []

        with self.registry._lock:
            for dev in self.registry._devices.values():
                if dev.device_type == common_pb2.UV_CHAMBER:
                    for ts, tmsg in dev.history:
                        if ts >= min_timestamp and tmsg.WhichOneof("payload") == "uv_chamber":
                            p = tmsg.uv_chamber
                            uvas.append(p.uva_intensity_mw_cm2)
                            uvbs.append(p.uvb_intensity_mw_cm2)
                            temps.append(p.ambient_temperature_celsius)
                            humids.append(p.ambient_humidity_percent)

        def calc_stats(values: List[float]) -> Tuple[float, float]:
            if not values:
                return 0.0, 0.0
            n = len(values)
            mean = sum(values) / n
            if n <= 1:
                return round(mean, 3), 0.0
            variance = sum((x - mean) ** 2 for x in values) / (n - 1)
            std_dev = math.sqrt(variance)
            return round(mean, 3), round(std_dev, 3)

        avg_uva, std_uva = calc_stats(uvas)
        avg_uvb, std_uvb = calc_stats(uvbs)
        avg_temp, std_temp = calc_stats(temps)
        avg_hum, std_hum = calc_stats(humids)

        return client_gateway_pb2.UvClimateAnalyticsResult(
            total_samples=len(uvas),
            avg_uva=avg_uva,
            std_dev_uva=std_uva,
            avg_uvb=avg_uvb,
            std_dev_uvb=std_uvb,
            avg_temperature=avg_temp,
            std_dev_temperature=std_temp,
            avg_humidity=avg_hum,
            std_dev_humidity=std_hum,
        )

    def _compute_device_incidents_summary(self) -> client_gateway_pb2.IncidentsAnalyticsResult:
        """Consulta 3: Ranking de incidentes imediatos e instabilidades das fontes."""
        items: List[Tuple[int, client_gateway_pb2.DeviceIncidentItem]] = []

        with self.registry._lock:
            for dev in self.registry._devices.values():
                err_count = 1 if dev.state in (common_pb2.STATE_ERROR, common_pb2.STATE_OFFLINE) else 0
                incident_item = client_gateway_pb2.DeviceIncidentItem(
                    device_id=dev.device_id,
                    device_type=dev.device_type,
                    immediate_alert_count=dev.immediate_alert_count,
                    error_state_count=err_count,
                    last_incident_description=dev.last_fault_reason or ("OFFLINE" if err_count else "NORMAL"),
                )
                severity_score = dev.immediate_alert_count * 10 + err_count * 5
                items.append((severity_score, incident_item))

        # Ordena de forma decrescente por índice de severidade/incidentes
        items.sort(key=lambda x: x[0], reverse=True)

        res = client_gateway_pb2.IncidentsAnalyticsResult()
        for _, item in items:
            added = res.devices_ranked.add()
            added.CopyFrom(item)

        if items and items[0][0] > 0:
            res.most_unstable_device_id = items[0][1].device_id
        else:
            res.most_unstable_device_id = "Nenhum incidente crítico registrado"

        return res
