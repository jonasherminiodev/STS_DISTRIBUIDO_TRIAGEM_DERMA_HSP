"""
Classe base para as Fontes de Dados Distribuídas.
Gerencia a escuta no grupo UDP Multicast, resposta de descoberta e envio UDP de telemetria.
"""
import os
import socket
import struct
import sys
import threading
import time
from typing import Optional

# Configura sys.path para garantir acesso aos protos gerados
_BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _BASE_DIR not in sys.path:
    sys.path.insert(0, _BASE_DIR)

from generated import common_pb2, discovery_pb2, telemetry_pb2


class BaseSource:
    """Implementa o comportamento de rede comum a todas as fontes de dados."""

    def __init__(
        self,
        device_id: str,
        device_type: common_pb2.DeviceType,
        grpc_port: int = 0,
        gateway_host: str = "127.0.0.1",
        gateway_telemetry_port: int = 9000,
        gateway_discovery_resp_port: int = 10001,
        multicast_group: str = "224.1.1.1",
        multicast_port: int = 10000,
        sampling_rate_seconds: float = 5.0,
        firmware_version: str = "1.0.0",
    ):
        self.device_id = device_id
        self.device_type = device_type
        self.grpc_port = grpc_port
        self.gateway_host = gateway_host
        self.gateway_telemetry_port = gateway_telemetry_port
        self.gateway_discovery_resp_port = gateway_discovery_resp_port
        self.multicast_group = multicast_group
        self.multicast_port = multicast_port
        self.sampling_rate_seconds = sampling_rate_seconds
        self.firmware_version = firmware_version

        self.state = common_pb2.STATE_ACTIVE
        self.sequence_number = 0
        self.start_time = time.time()
        self._running = False

        self._udp_sock: Optional[socket.socket] = None
        self._multicast_sock: Optional[socket.socket] = None
        self._multicast_thread: Optional[threading.Thread] = None
        self._telemetry_thread: Optional[threading.Thread] = None

    def start(self):
        """Inicia os sockets de rede e as threads de trabalho."""
        if self._running:
            return
        self._running = True

        # Socket UDP Unicast para envio de telemetria e respostas de descoberta
        self._udp_sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)

        # Inicia escuta no grupo UDP Multicast para responder solicitações de descoberta
        self._start_multicast_listener()

        # Inicia loop periódico de telemetria
        self._telemetry_thread = threading.Thread(
            target=self._periodic_telemetry_loop,
            name=f"TelemetryLoop-{self.device_id}",
            daemon=True,
        )
        self._telemetry_thread.start()

    def _start_multicast_listener(self):
        """Configura socket para escutar requisições de descoberta enviadas no grupo multicast."""
        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM, socket.IPPROTO_UDP)
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            if hasattr(socket, "SO_REUSEPORT"):
                try:
                    sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEPORT, 1)
                except OSError:
                    pass

            sock.bind(("", self.multicast_port))

            # Adiciona socket ao grupo multicast
            mreq = struct.pack("4sl", socket.inet_aton(self.multicast_group), socket.INADDR_ANY)
            sock.setsockopt(socket.IPPROTO_IP, socket.IP_ADD_MEMBERSHIP, mreq)
            sock.settimeout(1.0)
            self._multicast_sock = sock

            self._multicast_thread = threading.Thread(
                target=self._multicast_listen_loop,
                name=f"MulticastListener-{self.device_id}",
                daemon=True,
            )
            self._multicast_thread.start()
        except Exception as e:
            # Caso a interface multicast não esteja disponível no ambiente, registra e continua
            pass

    def _multicast_listen_loop(self):
        """Aguarda mensagens DiscoveryRequest do Gateway e responde com DiscoveryResponse."""
        while self._running and self._multicast_sock:
            try:
                data, addr = self._multicast_sock.recvfrom(4096)
                req = discovery_pb2.DiscoveryRequest()
                req.ParseFromString(data)

                # Responde à descoberta
                self.send_discovery_response()
            except socket.timeout:
                continue
            except Exception:
                if not self._running:
                    break

    def send_discovery_response(self):
        """Envia DiscoveryResponse serializado via UDP unicast para o Gateway."""
        if not self._udp_sock or not self._running:
            return

        resp = discovery_pb2.DiscoveryResponse(
            device_id=self.device_id,
            device_type=self.device_type,
            ip_address="127.0.0.1",
            grpc_port=self.grpc_port,
            initial_state=self.state,
            firmware_version=self.firmware_version,
        )
        payload = resp.SerializeToString()
        try:
            self._udp_sock.sendto(payload, (self.gateway_host, self.gateway_discovery_resp_port))
        except Exception:
            pass

    def send_telemetry(self, telemetry_msg: telemetry_pb2.TelemetryMessage):
        """Envia uma mensagem de telemetria serializada via socket UDP unicast ao Gateway."""
        if not self._udp_sock or not self._running:
            return

        self.sequence_number += 1
        telemetry_msg.header.device_id = self.device_id
        telemetry_msg.header.device_type = self.device_type
        telemetry_msg.header.timestamp_utc = int(time.time())
        telemetry_msg.header.sequence_number = self.sequence_number

        payload = telemetry_msg.SerializeToString()
        try:
            self._udp_sock.sendto(payload, (self.gateway_host, self.gateway_telemetry_port))
        except Exception:
            pass

    def generate_telemetry_payload(self) -> telemetry_pb2.TelemetryMessage:
        """Método abstrato implementado pelas subclasses para gerar a leitura específica."""
        raise NotImplementedError("Subclasses devem implementar generate_telemetry_payload")

    def _periodic_telemetry_loop(self):
        """Loop periódico de envio de telemetria."""
        # Envia uma resposta de descoberta inicial voluntária ao ligar
        self.send_discovery_response()

        while self._running:
            if self.state == common_pb2.STATE_ACTIVE:
                try:
                    msg = self.generate_telemetry_payload()
                    msg.is_immediate_alert = False
                    self.send_telemetry(msg)
                except Exception:
                    pass

            time.sleep(self.sampling_rate_seconds)

    def stop(self):
        """Encerra threads e fecha sockets de rede."""
        self._running = False
        if self._multicast_sock:
            try:
                self._multicast_sock.close()
            except Exception:
                pass
        if self._udp_sock:
            try:
                self._udp_sock.close()
            except Exception:
                pass
        if self._telemetry_thread and self._telemetry_thread.is_alive():
            self._telemetry_thread.join(timeout=2.0)
        if self._multicast_thread and self._multicast_thread.is_alive():
            self._multicast_thread.join(timeout=2.0)
