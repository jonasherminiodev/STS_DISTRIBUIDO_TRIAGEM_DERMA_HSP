"""
Receptor UDP Unicast de Telemetria Contínua do Gateway.
Escuta datagramas UDP na porta designada, desserializa via Protocol Buffers e encaminha ao DeviceRegistry.
"""
import socket
import threading
from typing import Callable, List, Optional

from generated import telemetry_pb2
from .device_registry import DeviceRegistry


class UDPTelemetryReceiver:
    """Receptor assíncrono de pacotes de telemetria UDP."""

    def __init__(
        self,
        registry: DeviceRegistry,
        bind_host: str = "0.0.0.0",
        port: int = 9000,
    ):
        self.registry = registry
        self.bind_host = bind_host
        self.port = port

        self._sock: Optional[socket.socket] = None
        self._running = False
        self._thread: Optional[threading.Thread] = None
        self._callbacks: List[Callable[[telemetry_pb2.TelemetryMessage], None]] = []

    def add_telemetry_callback(self, callback: Callable[[telemetry_pb2.TelemetryMessage], None]):
        """Adiciona um observer para ser notificado de novas telemetrias (ex: logger, analítica)."""
        self._callbacks.append(callback)

    def start(self):
        """Inicializa o socket UDP e inicia a thread de escuta."""
        if self._running:
            return
        self._running = True

        self._sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self._sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        if hasattr(socket, "SO_REUSEPORT"):
            try:
                self._sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEPORT, 1)
            except OSError:
                pass

        self._sock.bind((self.bind_host, self.port))
        self._sock.settimeout(1.0)

        self._thread = threading.Thread(
            target=self._listen_loop, name="UDPTelemetryReceiverThread", daemon=True
        )
        self._thread.start()

    def _listen_loop(self):
        """Loop contínuo de recepção de datagramas UDP."""
        while self._running:
            try:
                data, addr = self._sock.recvfrom(65535)
                msg = telemetry_pb2.TelemetryMessage()
                msg.ParseFromString(data)

                # Registra na tabela em memória do Gateway
                self.registry.record_telemetry(msg)

                # Dispara callbacks registrados
                for cb in self._callbacks:
                    try:
                        cb(msg)
                    except Exception:
                        pass
            except socket.timeout:
                continue
            except Exception:
                if not self._running:
                    break

    def stop(self):
        """Encerra o socket e aguarda a finalização da thread."""
        self._running = False
        if self._sock:
            try:
                self._sock.close()
            except Exception:
                pass
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=2.0)
