"""
Fonte 2: Sensor de Cabine UV / Fototerapia (Fonte Não Controlável - Sensor Contínuo).
Transmite periodicamente leituras ambientais e dosimétricas de radiação UVA/UVB via UDP.
"""
import argparse
import random
import sys
import time

from generated import common_pb2, telemetry_pb2
from .base_source import BaseSource


class UvChamberSource(BaseSource):
    """Fonte não controlável simulando sensor de câmara de fototerapia dermatológica."""

    def __init__(
        self,
        device_id: str = "UV-CHAMBER-01",
        gateway_host: str = "127.0.0.1",
        gateway_telemetry_port: int = 9000,
        gateway_discovery_resp_port: int = 10001,
        multicast_group: str = "224.1.1.1",
        multicast_port: int = 10000,
        sampling_rate_seconds: float = 5.0,
    ):
        super().__init__(
            device_id=device_id,
            device_type=common_pb2.UV_CHAMBER,
            grpc_port=0,  # Não controlável: não expõe servidor gRPC
            gateway_host=gateway_host,
            gateway_telemetry_port=gateway_telemetry_port,
            gateway_discovery_resp_port=gateway_discovery_resp_port,
            multicast_group=multicast_group,
            multicast_port=multicast_port,
            sampling_rate_seconds=sampling_rate_seconds,
            firmware_version="2.1.0-phototherapy",
        )
        self.base_uva = 3.2
        self.base_uvb = 0.45
        self.base_temp = 23.5
        self.base_humidity = 50.0

    def generate_telemetry_payload(self) -> telemetry_pb2.TelemetryMessage:
        """Gera leituras dosimétricas e ambientais com variações naturais realistas."""
        msg = telemetry_pb2.TelemetryMessage()

        payload = msg.uv_chamber
        # Simula flutuações pequenas de intensidade e ambiente
        payload.uva_intensity_mw_cm2 = round(self.base_uva + random.uniform(-0.15, 0.15), 3)
        payload.uvb_intensity_mw_cm2 = round(self.base_uvb + random.uniform(-0.03, 0.03), 3)
        payload.ambient_temperature_celsius = round(self.base_temp + random.uniform(-0.4, 0.4), 2)
        payload.ambient_humidity_percent = round(self.base_humidity + random.uniform(-1.5, 1.5), 1)
        payload.safety_door_closed = True

        return msg


def main():
    parser = argparse.ArgumentParser(description="Fonte 2: Sensor de Cabine UV / Fototerapia (Não Controlável)")
    parser.add_argument("--device-id", default="UV-CHAMBER-01", help="Identificador da fonte")
    parser.add_argument("--gateway-host", default="127.0.0.1", help="Endereço do Gateway")
    parser.add_argument("--gateway-port", type=int, default=9000, help="Porta UDP do Gateway")
    parser.add_argument("--discovery-port", type=int, default=10001, help="Porta de resposta de descoberta")
    parser.add_argument("--sampling-rate", type=float, default=5.0, help="Intervalo de envio em segundos")

    args = parser.parse_args()

    print(f"[+] Iniciando Fonte 2 [{args.device_id}] (Não Controlável)...")
    source = UvChamberSource(
        device_id=args.device_id,
        gateway_host=args.gateway_host,
        gateway_telemetry_port=args.gateway_port,
        gateway_discovery_resp_port=args.discovery_port,
        sampling_rate_seconds=args.sampling_rate,
    )
    source.start()

    try:
        while True:
            time.sleep(1.0)
    except KeyboardInterrupt:
        print("\n[!] Encerrando Fonte 2...")
        source.stop()
        print("[✓] Fonte 2 finalizada com sucesso.")


if __name__ == "__main__":
    main()
