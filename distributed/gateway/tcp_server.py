"""
Servidor TCP do Gateway para atendimento a Clientes (CLI e Web).
Implementa protocolo de aplicação com enquadramento por prefixo de tamanho (Length-Prefixed Framing)
e serialização estrita via Protocol Buffers.
"""
import socket
import struct
import threading
from typing import Optional

from generated import client_gateway_pb2
from .device_registry import DeviceRegistry
from .grpc_client import GatewayGRPCController
from .analytics_engine import AnalyticsEngine


def recv_exact(sock: socket.socket, num_bytes: int) -> Optional[bytes]:
    """Lê exatamente num_bytes de um stream TCP, tratando fragmentação."""
    data = bytearray()
    while len(data) < num_bytes:
        packet = sock.recv(num_bytes - len(data))
        if not packet:
            return None
        data.extend(packet)
    return bytes(data)


def send_length_prefixed(sock: socket.socket, payload: bytes):
    """Envia payload binário precedido por 4 bytes big-endian indicando seu tamanho exato."""
    prefix = struct.pack(">I", len(payload))
    sock.sendall(prefix + payload)


class GatewayTCPServer:
    """Servidor TCP multithread para comunicação Cliente-Gateway."""

    def __init__(
        self,
        registry: DeviceRegistry,
        grpc_controller: GatewayGRPCController,
        analytics_engine: AnalyticsEngine,
        bind_host: str = "0.0.0.0",
        port: int = 8000,
    ):
        self.registry = registry
        self.grpc_controller = grpc_controller
        self.analytics_engine = analytics_engine
        self.bind_host = bind_host
        self.port = port

        self._server_sock: Optional[socket.socket] = None
        self._running = False
        self._accept_thread: Optional[threading.Thread] = None

    def start(self):
        """Inicia socket TCP passivo e thread accept."""
        if self._running:
            return
        self._running = True

        self._server_sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self._server_sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        if hasattr(socket, "SO_REUSEPORT"):
            try:
                self._server_sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEPORT, 1)
            except OSError:
                pass

        self._server_sock.bind((self.bind_host, self.port))
        self._server_sock.listen(10)
        self._server_sock.settimeout(1.0)

        self._accept_thread = threading.Thread(
            target=self._accept_loop, name="GatewayTCPAcceptThread", daemon=True
        )
        self._accept_thread.start()

    def _accept_loop(self):
        """Loop principal de aceitação de conexões de clientes TCP."""
        while self._running and self._server_sock:
            try:
                client_sock, client_addr = self._server_sock.accept()
                client_handler = threading.Thread(
                    target=self._handle_client,
                    args=(client_sock, client_addr),
                    name=f"TCPClientHandler-{client_addr[0]}:{client_addr[1]}",
                    daemon=True,
                )
                client_handler.start()
            except socket.timeout:
                continue
            except Exception:
                if not self._running:
                    break

    def _handle_client(self, client_sock: socket.socket, client_addr):
        """Processa requisições de um cliente conectado até o encerramento da conexão."""
        client_sock.settimeout(30.0)
        try:
            while self._running:
                # 1. Lê os 4 bytes de cabeçalho indicando o tamanho do payload
                prefix = recv_exact(client_sock, 4)
                if not prefix:
                    break  # Conexão encerrada pelo cliente

                msg_len = struct.unpack(">I", prefix)[0]

                # 2. Lê exatamente msg_len bytes contendo o ClientRequest Protobuf
                payload = recv_exact(client_sock, msg_len)
                if not payload:
                    break

                request = client_gateway_pb2.ClientRequest()
                request.ParseFromString(payload)

                # 3. Processa a requisição e monta a resposta
                response = self._process_request(request)

                # 4. Serializa e envia a resposta com enquadramento de tamanho
                resp_bytes = response.SerializeToString()
                send_length_prefixed(client_sock, resp_bytes)
        except Exception:
            pass
        finally:
            try:
                client_sock.close()
            except Exception:
                pass

    def _process_request(self, request: client_gateway_pb2.ClientRequest) -> client_gateway_pb2.GatewayResponse:
        """Roteia o comando do cliente para o subsistema correspondente."""
        cmd = request.command
        response = client_gateway_pb2.GatewayResponse(
            request_id=request.request_id,
            status=client_gateway_pb2.STATUS_OK,
            message="Operação realizada com sucesso",
        )

        # 1. Listagem de fontes conectadas
        if cmd == client_gateway_pb2.CMD_LIST_DEVICES:
            devices = self.registry.list_devices_proto()
            for dev in devices:
                item = response.devices.add()
                item.CopyFrom(dev)
            response.message = f"{len(devices)} dispositivos encontrados no ambiente."

        # 2. Envio de comando gRPC para uma fonte específica
        elif cmd == client_gateway_pb2.CMD_SEND_DEVICE_CONTROL:
            target_id = request.target_device_id
            success, config_resp = self.grpc_controller.send_config_command(
                target_device_id=target_id,
                config_request=request.device_config,
            )
            response.config_response.CopyFrom(config_resp)
            if not success:
                response.status = client_gateway_pb2.STATUS_ERROR
                response.message = config_resp.message

        # 3. Consulta analítica agregada
        elif cmd == client_gateway_pb2.CMD_ANALYTICS_QUERY:
            q_type = request.analytics_query.query_type
            w_sec = request.analytics_query.time_window_seconds
            analytics_res = self.analytics_engine.compute_query(q_type, w_sec)
            response.analytics.CopyFrom(analytics_res)
            response.message = f"Consulta analítica {q_type} processada com sucesso."

        else:
            response.status = client_gateway_pb2.STATUS_ERROR
            response.message = f"Comando desconhecido: {cmd}"

        return response

    def stop(self):
        """Finaliza o servidor TCP."""
        self._running = False
        if self._server_sock:
            try:
                self._server_sock.close()
            except Exception:
                pass
        if self._accept_thread and self._accept_thread.is_alive():
            self._accept_thread.join(timeout=2.0)
