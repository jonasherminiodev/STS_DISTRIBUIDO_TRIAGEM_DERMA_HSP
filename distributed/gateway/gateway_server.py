"""
Servidor Gateway Central do Sistema Distribuído.
Orquestra o registro de dispositivos, descoberta multicast, recepção UDP de telemetria,
atendimento TCP a clientes e despacho gRPC de comandos de controle.
"""
import threading
import time
from typing import Optional

from .device_registry import DeviceRegistry
from .multicast_discovery import MulticastDiscoveryManager
from .udp_receiver import UDPTelemetryReceiver
from .grpc_client import GatewayGRPCController
from .analytics_engine import AnalyticsEngine
from .tcp_server import GatewayTCPServer
from .persistence import GatewayStorage


class GatewayServer:
    """Núcleo do Gateway Central de Gestão Inteligente."""

    def __init__(
        self,
        tcp_port: int = 8000,
        multicast_group: str = "224.1.1.1",
        multicast_port: int = 10000,
        discovery_response_port: int = 10001,
        udp_telemetry_port: int = 9000,
        offline_timeout_seconds: float = 30.0,
        gateway_id: str = "GATEWAY-CENTRAL-01",
        db_path: Optional[str] = None,
    ):
        self.gateway_id = gateway_id
        self.registry = DeviceRegistry(offline_timeout_seconds=offline_timeout_seconds)
        self.storage = GatewayStorage(db_path=db_path)

        self.grpc_controller = GatewayGRPCController(registry=self.registry)
        self.analytics_engine = AnalyticsEngine(registry=self.registry)

        self.discovery = MulticastDiscoveryManager(
            registry=self.registry,
            multicast_group=multicast_group,
            multicast_port=multicast_port,
            response_port=discovery_response_port,
            gateway_id=gateway_id,
        )

        self.telemetry_receiver = UDPTelemetryReceiver(
            registry=self.registry,
            port=udp_telemetry_port,
        )

        # Conecta callback para persistir leituras no banco SQLite
        self.telemetry_receiver.add_telemetry_callback(self.storage.store_telemetry)

        self.tcp_server = GatewayTCPServer(
            registry=self.registry,
            grpc_controller=self.grpc_controller,
            analytics_engine=self.analytics_engine,
            port=tcp_port,
        )

        self._running = False
        self._heartbeat_thread: Optional[threading.Thread] = None

    def start(self):
        """Inicia todos os subsistemas do Gateway."""
        if self._running:
            return
        self._running = True

        # Inicia receptor de telemetria UDP
        self.telemetry_receiver.start()

        # Inicia agente de descoberta multicast
        self.discovery.start()

        # Inicia servidor TCP para clientes
        self.tcp_server.start()

        # Dispara descoberta inicial imediatamente
        self.broadcast_discovery()

        # Inicia monitor de inatividade (heartbeat)
        self._heartbeat_thread = threading.Thread(
            target=self._heartbeat_loop, name="GatewayHeartbeatMonitor", daemon=True
        )
        self._heartbeat_thread.start()

    def broadcast_discovery(self):
        """Envia pacote multicast solicitando identificação de todas as fontes."""
        self.discovery.broadcast_solicitation()

    def _heartbeat_loop(self):
        """Loop que verifica periodicamente dispositivos inativos e marca como OFFLINE."""
        while self._running:
            time.sleep(2.0)
            if not self._running:
                break
            self.registry.check_timeouts()

    def stop(self):
        """Encerra graciosamente todos os serviços do Gateway."""
        self._running = False
        self.discovery.stop()
        self.telemetry_receiver.stop()
        self.tcp_server.stop()
        if self._heartbeat_thread and self._heartbeat_thread.is_alive():
            self._heartbeat_thread.join(timeout=2.0)
