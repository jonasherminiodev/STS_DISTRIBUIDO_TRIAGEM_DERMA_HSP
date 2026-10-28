"""
Fonte 1: Estação de Dermatoscopia Digital com IA (Fonte Controlável via gRPC).
Expõe um servidor gRPC para controle de parâmetros operacionais pelo Gateway e transmite
telemetria contínua com laudos de classificação de lesões cutâneas via UDP.
"""
import argparse
from concurrent import futures
import random
import sys
import time
from typing import Optional
import grpc

from generated import common_pb2, device_control_pb2, device_control_pb2_grpc, telemetry_pb2
from .base_source import BaseSource
from .ai_inference_adapter import AIInferenceAdapter


class DermatoscopyControlServicer(device_control_pb2_grpc.DeviceControlServicer):
    """Implementação do serviço gRPC DeviceControl para controle da Estação de Dermatoscopia."""

    def __init__(self, source: "DermatoscopySource"):
        self.source = source

    def ConfigureDevice(self, request, context):
        """Recebe e processa comandos de configuração enviados pelo Gateway via gRPC."""
        action = request.action
        msg = "Comando executado com sucesso"

        if action == device_control_pb2.ACTIVATE:
            self.source.state = common_pb2.STATE_ACTIVE
            msg = "Estação de Dermatoscopia ativada."
        elif action == device_control_pb2.DEACTIVATE:
            self.source.state = common_pb2.STATE_IDLE
            msg = "Estação de Dermatoscopia colocada em repouso (IDLE)."
        elif action == device_control_pb2.SET_SAMPLING_RATE:
            if request.new_sampling_rate_seconds > 0:
                self.source.sampling_rate_seconds = round(float(request.new_sampling_rate_seconds), 2)
                msg = f"Taxa de amostragem alterada para {self.source.sampling_rate_seconds:.1f}s."
            else:
                return device_control_pb2.DeviceConfigResponse(
                    success=False,
                    message="Taxa de amostragem inválida (deve ser > 0)",
                    current_state=self.source.state,
                )
        elif action == device_control_pb2.SET_ALERT_THRESHOLD:
            if 0.0 <= request.new_malignancy_threshold <= 1.0:
                self.source.malignancy_threshold = float(request.new_malignancy_threshold)
                msg = f"Limiar de malignidade alterado para {self.source.malignancy_threshold:.2f}."
            else:
                return device_control_pb2.DeviceConfigResponse(
                    success=False,
                    message="Limiar deve estar entre 0.0 e 1.0",
                    current_state=self.source.state,
                )
        elif action == device_control_pb2.SIMULATE_FAULT:
            self.source.state = common_pb2.STATE_ERROR
            self.source.last_fault_reason = request.fault_simulation_mode or "FALHA_SENSOR_OTICO_DESCALIBRADO"
            msg = f"Simulação de falha acionada: {self.source.last_fault_reason}"
        elif action == device_control_pb2.RESET:
            self.source.state = common_pb2.STATE_ACTIVE
            self.source.last_fault_reason = ""
            msg = "Dispositivo resetado com sucesso para estado ativo."
        else:
            return device_control_pb2.DeviceConfigResponse(
                success=False,
                message=f"Ação desconhecida: {action}",
                current_state=self.source.state,
            )

        print(f"[gRPC Control] {self.source.device_id}: {msg}")
        return device_control_pb2.DeviceConfigResponse(
            success=True,
            message=msg,
            current_state=self.source.state,
            effective_sampling_rate=self.source.sampling_rate_seconds,
            effective_threshold=self.source.malignancy_threshold,
        )

    def GetDeviceState(self, request, context):
        """Reporta estado operacional e métricas para o Gateway via gRPC."""
        uptime = int(time.time() - self.source.start_time)
        return device_control_pb2.DeviceStateResponse(
            device_id=self.source.device_id,
            device_type=self.source.device_type,
            state=self.source.state,
            sampling_rate_seconds=self.source.sampling_rate_seconds,
            alert_threshold=self.source.malignancy_threshold,
            uptime_seconds=uptime,
            total_messages_sent=self.source.sequence_number,
            last_fault_reason=self.source.last_fault_reason,
        )


class DermatoscopySource(BaseSource):
    """Estação de Dermatoscopia Digital com IA (Controlável via gRPC e telemetria contínua via UDP)."""

    def __init__(
        self,
        device_id: str = "DERMATOSCOPY-01",
        grpc_port: int = 50051,
        gateway_host: str = "127.0.0.1",
        gateway_telemetry_port: int = 9000,
        gateway_discovery_resp_port: int = 10001,
        multicast_group: str = "224.1.1.1",
        multicast_port: int = 10000,
        sampling_rate_seconds: float = 5.0,
        malignancy_threshold: float = 0.70,
        force_simulation: bool = False,
    ):
        super().__init__(
            device_id=device_id,
            device_type=common_pb2.DERMATOSCOPY_AI,
            grpc_port=grpc_port,
            gateway_host=gateway_host,
            gateway_telemetry_port=gateway_telemetry_port,
            gateway_discovery_resp_port=gateway_discovery_resp_port,
            multicast_group=multicast_group,
            multicast_port=multicast_port,
            sampling_rate_seconds=sampling_rate_seconds,
            firmware_version="3.0.0-ai-resnet",
        )
        self.malignancy_threshold = malignancy_threshold
        self.last_fault_reason = ""
        self.total_scans = 0

        self.ai_adapter = AIInferenceAdapter(force_simulation=force_simulation)
        self._grpc_server: Optional[grpc.Server] = None

    def start(self):
        """Inicia servidor gRPC e componentes base de rede."""
        # 1. Inicia o servidor gRPC
        self._grpc_server = grpc.server(futures.ThreadPoolExecutor(max_workers=4))
        device_control_pb2_grpc.add_DeviceControlServicer_to_server(
            DermatoscopyControlServicer(self), self._grpc_server
        )
        self._grpc_server.add_insecure_port(f"0.0.0.0:{self.grpc_port}")
        self._grpc_server.start()
        print(f"[gRPC Server] Estação {self.device_id} escutando na porta {self.grpc_port}")

        # 2. Inicia sockets UDP e multicast
        super().start()

    def generate_telemetry_payload(self) -> telemetry_pb2.TelemetryMessage:
        """Gera leitura com dados do sensor ótico e laudo de classificação de IA."""
        msg = telemetry_pb2.TelemetryMessage()
        self.total_scans += 1

        payload = msg.dermatoscopy
        payload.sensor_temperature_celsius = round(33.0 + random.uniform(-0.8, 0.8), 2)
        payload.led_intensity_lux = round(800.0 + random.uniform(-20.0, 20.0), 1)
        payload.battery_percent = max(10.0, round(100.0 - (self.total_scans * 0.1), 1))
        payload.total_examinations = self.total_scans

        # Executa classificação dermatológica via adaptador de IA
        top_class, top_prob, is_mal, probs, img_name = self.ai_adapter.classify_random_sample()

        pred = payload.latest_prediction
        pred.top_class = top_class
        pred.top_probability = top_prob
        pred.is_malignant = is_mal
        pred.image_reference = img_name

        for cid, cname, cprob in probs:
            p_item = pred.probabilities.add()
            p_item.class_id = cid
            p_item.class_name = cname
            p_item.probability = cprob

        return msg

    def stop(self):
        """Encerra servidor gRPC e sockets de rede."""
        super().stop()
        if self._grpc_server:
            self._grpc_server.stop(grace=1.0)
            print(f"[gRPC Server] Estação {self.device_id} finalizada.")


def main():
    parser = argparse.ArgumentParser(description="Fonte 1: Estação de Dermatoscopia Digital com IA (Controlável via gRPC)")
    parser.add_argument("--device-id", default="DERMATOSCOPY-01", help="Identificador da fonte")
    parser.add_argument("--grpc-port", type=int, default=50051, help="Porta do servidor gRPC")
    parser.add_argument("--gateway-host", default="127.0.0.1", help="Endereço do Gateway")
    parser.add_argument("--gateway-port", type=int, default=9000, help="Porta UDP do Gateway")
    parser.add_argument("--discovery-port", type=int, default=10001, help="Porta de resposta de descoberta")
    parser.add_argument("--sampling-rate", type=float, default=5.0, help="Intervalo de envio em segundos")

    args = parser.parse_args()

    print(f"[+] Iniciando Fonte 1 [{args.device_id}] (Controlável via gRPC porta {args.grpc_port})...")
    source = DermatoscopySource(
        device_id=args.device_id,
        grpc_port=args.grpc_port,
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
        print("\n[!] Encerrando Fonte 1...")
        source.stop()
        print("[✓] Fonte 1 finalizada com sucesso.")


if __name__ == "__main__":
    main()
