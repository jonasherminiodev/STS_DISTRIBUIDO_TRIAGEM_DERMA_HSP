"""
Fonte 3: Monitor de Lesão Dérmica / Patch Dérmico Conectado.
Implementa envio periódico via UDP e disparo IMEDIATO ao detectar anomalia crítica (hipertermia local).
"""
import argparse
import random
import sys
import threading
import time

from generated import common_pb2, telemetry_pb2
from .base_source import BaseSource


class PatchSensorSource(BaseSource):
    """Fonte que transmite telemetria periódica e dispara alerta imediato em evento crítico."""

    def __init__(
        self,
        device_id: str = "PATCH-01",
        gateway_host: str = "127.0.0.1",
        gateway_telemetry_port: int = 9000,
        gateway_discovery_resp_port: int = 10001,
        multicast_group: str = "224.1.1.1",
        multicast_port: int = 10000,
        sampling_rate_seconds: float = 5.0,
        alert_threshold_celsius: float = 38.5,
    ):
        super().__init__(
            device_id=device_id,
            device_type=common_pb2.PATCH_SENSOR,
            grpc_port=0,
            gateway_host=gateway_host,
            gateway_telemetry_port=gateway_telemetry_port,
            gateway_discovery_resp_port=gateway_discovery_resp_port,
            multicast_group=multicast_group,
            multicast_port=multicast_port,
            sampling_rate_seconds=sampling_rate_seconds,
            firmware_version="1.4.2-patch",
        )
        self.alert_threshold_celsius = alert_threshold_celsius
        self.current_temperature = 36.6
        self.current_impedance = 1350.0
        self.current_hydration = 30.0

    def generate_telemetry_payload(self) -> telemetry_pb2.TelemetryMessage:
        """Gera leitura periódica normal de impedância e temperatura tecidual."""
        msg = telemetry_pb2.TelemetryMessage()

        payload = msg.patch_sensor
        # Variações fisiológicas normais
        payload.lesion_temperature_celsius = round(self.current_temperature + random.uniform(-0.15, 0.15), 2)
        payload.tissue_impedance_ohms = round(self.current_impedance + random.uniform(-20.0, 20.0), 1)
        payload.hydration_percent = round(self.current_hydration + random.uniform(-1.0, 1.0), 1)
        payload.alert_trigger = ""

        return msg

    def trigger_critical_event(
        self,
        temperature_celsius: float = 39.5,
        reason: str = "HIPERTERMIA_LOCAL_CRITICA",
    ):
        """Dispara IMEDIATAMENTE uma mensagem de alerta crítico fora do ciclo periódico normal."""
        if not self._running:
            return

        msg = telemetry_pb2.TelemetryMessage()
        msg.is_immediate_alert = True  # Marca envio imediato

        payload = msg.patch_sensor
        payload.lesion_temperature_celsius = float(temperature_celsius)
        payload.tissue_impedance_ohms = 850.0  # Queda brusca de impedância por edema inflamatório
        payload.hydration_percent = 15.0
        payload.alert_trigger = reason

        print(f"[!] ALERTA IMEDIATO DISPARADO: {reason} ({temperature_celsius}°C) -> Enviando pacote UDP ao Gateway...")
        self.send_telemetry(msg)


def main():
    parser = argparse.ArgumentParser(description="Fonte 3: Patch Dérmico Conectado (Alerta Imediato + Periódico)")
    parser.add_argument("--device-id", default="PATCH-01", help="Identificador da fonte")
    parser.add_argument("--gateway-host", default="127.0.0.1", help="Endereço do Gateway")
    parser.add_argument("--gateway-port", type=int, default=9000, help="Porta UDP do Gateway")
    parser.add_argument("--discovery-port", type=int, default=10001, help="Porta de resposta de descoberta")
    parser.add_argument("--sampling-rate", type=float, default=5.0, help="Intervalo de envio em segundos")
    parser.add_argument("--auto-trigger-after", type=int, default=0, help="Disparar alerta anômalo automaticamente após N segundos (0 desativa)")

    args = parser.parse_args()

    print(f"[+] Iniciando Fonte 3 [{args.device_id}] (Envio Imediato + Periódico)...")
    source = PatchSensorSource(
        device_id=args.device_id,
        gateway_host=args.gateway_host,
        gateway_telemetry_port=args.gateway_port,
        gateway_discovery_resp_port=args.discovery_port,
        sampling_rate_seconds=args.sampling_rate,
    )
    source.start()

    if args.auto_trigger_after > 0:
        def auto_alert():
            time.sleep(args.auto_trigger_after)
            source.trigger_critical_event(39.6, "HIPERTERMIA_LOCAL_CRITICA")

        threading.Thread(target=auto_alert, daemon=True).start()

    try:
        while True:
            time.sleep(1.0)
    except KeyboardInterrupt:
        print("\n[!] Encerrando Fonte 3...")
        source.stop()
        print("[✓] Fonte 3 finalizada com sucesso.")


if __name__ == "__main__":
    main()
