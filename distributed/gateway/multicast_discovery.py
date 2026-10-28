"""
Módulo de Descoberta Dinâmica de Dispositivos via UDP Multicast.
Implementa a solicitação periódica ou inicial do Gateway e a recepção das respostas das fontes.
"""
import socket
import struct
import threading
import time
from typing import Optional

from generated import discovery_pb2
from .device_registry import DeviceRegistry


class MulticastDiscoveryManager:
    """Gerenciador de descoberta multicast do Gateway."""

    def __init__(
        self,
        registry: DeviceRegistry,
        multicast_group: str = "224.1.1.1",
        multicast_port: int = 10000,
        response_port: int = 10001,
        gateway_id: str = "GATEWAY-CENTRAL-01",
    ):
        self.registry = registry
        self.multicast_group = multicast_group
        self.multicast_port = multicast_port
        self.response_port = response_port
        self.gateway_id = gateway_id

        self._running = False
        self._sender_sock: Optional[socket.socket] = None
        self._listener_sock: Optional[socket.socket] = None
        self._listener_thread: Optional[threading.Thread] = None

    def start(self):
        """Inicia socket de envio multicast e thread de recepção de respostas unicast."""
        if self._running:
            return
        self._running = True

        # Socket para envio multicast
        self._sender_sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM, socket.IPPROTO_UDP)
        # Habilita TTL de multicast para permitir loopback e LAN
        ttl = struct.pack("b", 2)
        self._sender_sock.setsockopt(socket.IPPROTO_IP, socket.IP_MULTICAST_TTL, ttl)
        # Permite loopback multicast na mesma máquina
        loop = struct.pack("b", 1)
        self._sender_sock.setsockopt(socket.IPPROTO_IP, socket.IP_MULTICAST_LOOP, loop)

        # Socket para escutar respostas de descoberta enviadas pelas fontes
        self._listener_sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM, socket.IPPROTO_UDP)
        self._listener_sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        if hasattr(socket, "SO_REUSEPORT"):
            try:
                self._listener_sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEPORT, 1)
            except OSError:
                pass

        self._listener_sock.bind(("0.0.0.0", self.response_port))
        self._listener_sock.settimeout(1.0)

        self._listener_thread = threading.Thread(
            target=self._listen_for_responses, name="MulticastDiscoveryListener", daemon=True
        )
        self._listener_thread.start()

    def broadcast_solicitation(self):
        """Envia solicitação de identificação para o grupo Multicast."""
        if not self._sender_sock:
            return

        req = discovery_pb2.DiscoveryRequest(
            gateway_id=self.gateway_id,
            timestamp_utc=int(time.time()),
        )
        payload = req.SerializeToString()
        try:
            self._sender_sock.sendto(payload, (self.multicast_group, self.multicast_port))
        except Exception as e:
            # Não quebra a aplicação caso haja erro temporário de rede
            pass

    def _listen_for_responses(self):
        """Loop que recebe respostas DiscoveryResponse enviadas pelas fontes."""
        while self._running:
            try:
                data, addr = self._listener_sock.recvfrom(4096)
                resp = discovery_pb2.DiscoveryResponse()
                resp.ParseFromString(data)

                # Se o IP vier como 0.0.0.0 ou vazio, usa o endereço real de onde veio o pacote
                resolved_ip = resp.ip_address if resp.ip_address and resp.ip_address != "0.0.0.0" else addr[0]

                self.registry.register_or_update(
                    device_id=resp.device_id,
                    device_type=resp.device_type,
                    ip_address=resolved_ip,
                    grpc_port=resp.grpc_port,
                    initial_state=resp.initial_state,
                )
            except socket.timeout:
                continue
            except Exception:
                if not self._running:
                    break

    def stop(self):
        """Finaliza os sockets e encerra threads de descoberta."""
        self._running = False
        if self._listener_sock:
            try:
                self._listener_sock.close()
            except Exception:
                pass
        if self._sender_sock:
            try:
                self._sender_sock.close()
            except Exception:
                pass
        if self._listener_thread and self._listener_thread.is_alive():
            self._listener_thread.join(timeout=2.0)
