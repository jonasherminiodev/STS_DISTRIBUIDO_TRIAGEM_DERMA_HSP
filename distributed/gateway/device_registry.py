"""
Registro central de dispositivos gerenciados pelo Gateway.
Mantém tabela de estado em memória com thread-safety e controle de expiração (heartbeat).
"""
import threading
import time
from typing import Dict, List, Optional
from collections import deque

from generated import common_pb2, client_gateway_pb2, telemetry_pb2


class RegisteredDevice:
    """Representação interna de uma fonte de dados registrada no Gateway."""

    def __init__(
        self,
        device_id: str,
        device_type: common_pb2.DeviceType,
        ip_address: str,
        grpc_port: int,
        initial_state: common_pb2.DeviceState,
        max_history: int = 500,
    ):
        self.device_id = device_id
        self.device_type = device_type
        self.ip_address = ip_address
        self.grpc_port = grpc_port
        self.state = initial_state
        self.registered_at = time.time()
        self.last_seen_utc = int(self.registered_at)
        self.total_telemetry_count = 0
        self.immediate_alert_count = 0
        self.last_fault_reason = ""
        self.history: deque = deque(maxlen=max_history)

    def record_telemetry(self, telemetry_msg: telemetry_pb2.TelemetryMessage):
        """Atualiza estado com nova leitura recebida via UDP."""
        self.last_seen_utc = telemetry_msg.header.timestamp_utc or int(time.time())
        self.total_telemetry_count += 1
        if telemetry_msg.is_immediate_alert:
            self.immediate_alert_count += 1
            if telemetry_msg.WhichOneof("payload") == "patch_sensor":
                self.last_fault_reason = telemetry_msg.patch_sensor.alert_trigger

        self.history.append((self.last_seen_utc, telemetry_msg))
        # Se estava offline ou degradado, volta a ativo caso não haja falha explícita
        if self.state in (common_pb2.STATE_OFFLINE, common_pb2.STATE_IDLE):
            self.state = common_pb2.STATE_ACTIVE

    def to_device_info_proto(self) -> client_gateway_pb2.DeviceInfo:
        """Converte o estado interno para o formato Protobuf DeviceInfo."""
        return client_gateway_pb2.DeviceInfo(
            device_id=self.device_id,
            device_type=self.device_type,
            ip_address=self.ip_address,
            grpc_port=self.grpc_port,
            state=self.state,
            last_seen_utc=self.last_seen_utc,
            total_telemetry_count=self.total_telemetry_count,
            immediate_alert_count=self.immediate_alert_count,
        )


class DeviceRegistry:
    """Tabela de estado thread-safe de todas as fontes de dados do ambiente inteligente."""

    def __init__(self, offline_timeout_seconds: float = 30.0):
        self._devices: Dict[str, RegisteredDevice] = {}
        self._lock = threading.Lock()
        self.offline_timeout_seconds = offline_timeout_seconds

    def register_or_update(
        self,
        device_id: str,
        device_type: common_pb2.DeviceType,
        ip_address: str,
        grpc_port: int,
        initial_state: common_pb2.DeviceState,
    ) -> RegisteredDevice:
        """Registra uma nova fonte descoberta ou atualiza endereço/porta."""
        with self._lock:
            if device_id in self._devices:
                dev = self._devices[device_id]
                dev.ip_address = ip_address
                dev.grpc_port = grpc_port
                dev.last_seen_utc = int(time.time())
                return dev
            dev = RegisteredDevice(
                device_id=device_id,
                device_type=device_type,
                ip_address=ip_address,
                grpc_port=grpc_port,
                initial_state=initial_state,
            )
            self._devices[device_id] = dev
            return dev

    def get_device(self, device_id: str) -> Optional[RegisteredDevice]:
        """Obtém referência para um dispositivo registrado."""
        with self._lock:
            return self._devices.get(device_id)

    def record_telemetry(self, telemetry_msg: telemetry_pb2.TelemetryMessage) -> bool:
        """Processa e registra uma leitura de telemetria recebida via UDP."""
        dev_id = telemetry_msg.header.device_id
        with self._lock:
            if dev_id not in self._devices:
                # Se ainda não descoberto por multicast, cria registro automático
                self._devices[dev_id] = RegisteredDevice(
                    device_id=dev_id,
                    device_type=telemetry_msg.header.device_type,
                    ip_address="unknown",
                    grpc_port=0,
                    initial_state=common_pb2.STATE_ACTIVE,
                )
            self._devices[dev_id].record_telemetry(telemetry_msg)
            return True

    def check_timeouts(self) -> List[str]:
        """Verifica dispositivos que não enviaram telemetria dentro do limiar de tempo."""
        now = time.time()
        newly_offline = []
        with self._lock:
            for dev in self._devices.values():
                if dev.state != common_pb2.STATE_OFFLINE:
                    if (now - dev.last_seen_utc) > self.offline_timeout_seconds:
                        dev.state = common_pb2.STATE_OFFLINE
                        newly_offline.append(dev.device_id)
        return newly_offline

    def list_devices_proto(self) -> List[client_gateway_pb2.DeviceInfo]:
        """Retorna lista de todos os dispositivos em formato Protobuf."""
        with self._lock:
            return [dev.to_device_info_proto() for dev in self._devices.values()]

    def count(self) -> int:
        with self._lock:
            return len(self._devices)
