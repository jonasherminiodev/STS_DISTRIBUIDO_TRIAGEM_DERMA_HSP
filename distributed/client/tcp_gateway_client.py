"""
Cliente TCP reutilizável para conexão com o Gateway Central.
Gerencia conexão via sockets TCP, codificação Protocol Buffers e Length-Prefixed Framing.
"""
import os
import socket
import struct
import sys
import uuid
from typing import List, Optional, Tuple

_BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _BASE_DIR not in sys.path:
    sys.path.insert(0, _BASE_DIR)

from generated import client_gateway_pb2, device_control_pb2


class TCPGatewayClient:
    """Encapsula operações do protocolo Cliente-Gateway via TCP."""

    def __init__(self, host: str = "127.0.0.1", port: int = 8000, timeout_seconds: float = 8.0):
        self.host = host
        self.port = port
        self.timeout_seconds = timeout_seconds

    def _send_request(self, request: client_gateway_pb2.ClientRequest) -> client_gateway_pb2.GatewayResponse:
        """Abre conexão TCP, envia a requisição enquadrada com tamanho e retorna a resposta."""
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(self.timeout_seconds)
        try:
            sock.connect((self.host, self.port))

            # 1. Serializa requisição Protobuf e envia com prefixo de 4 bytes
            payload = request.SerializeToString()
            prefix = struct.pack(">I", len(payload))
            sock.sendall(prefix + payload)

            # 2. Lê os 4 bytes de tamanho da resposta
            resp_prefix = self._recv_exact(sock, 4)
            if not resp_prefix:
                raise ConnectionError("Gateway encerrou a conexão sem enviar dados de resposta.")

            resp_len = struct.unpack(">I", resp_prefix)[0]

            # 3. Lê o payload completo da resposta
            resp_payload = self._recv_exact(sock, resp_len)
            if not resp_payload:
                raise ConnectionError("Resposta incompleta recebida do Gateway.")

            response = client_gateway_pb2.GatewayResponse()
            response.ParseFromString(resp_payload)
            return response
        finally:
            try:
                sock.close()
            except Exception:
                pass

    def _recv_exact(self, sock: socket.socket, num_bytes: int) -> Optional[bytes]:
        """Lê exatamente num_bytes tratando fragmentações de rede no stream TCP."""
        data = bytearray()
        while len(data) < num_bytes:
            chunk = sock.recv(num_bytes - len(data))
            if not chunk:
                return None
            data.extend(chunk)
        return bytes(data)

    def list_devices(self) -> Tuple[bool, List[client_gateway_pb2.DeviceInfo], str]:
        """Solicita a lista de fontes de dados conectadas ao Gateway."""
        req = client_gateway_pb2.ClientRequest(
            request_id=f"LIST-{uuid.uuid4().hex[:6]}",
            command=client_gateway_pb2.CMD_LIST_DEVICES,
        )
        try:
            resp = self._send_request(req)
            if resp.status == client_gateway_pb2.STATUS_OK:
                return True, list(resp.devices), resp.message
            return False, [], resp.message
        except Exception as e:
            return False, [], str(e)

    def send_device_control(
        self,
        target_device_id: str,
        action: device_control_pb2.ControlAction,
        new_sampling_rate_seconds: float = 0.0,
        new_malignancy_threshold: float = 0.0,
        fault_simulation_mode: str = "",
    ) -> Tuple[bool, device_control_pb2.DeviceConfigResponse, str]:
        """Envia comando de configuração para uma fonte controlável via Gateway/gRPC."""
        cfg_req = device_control_pb2.DeviceConfigRequest(
            target_device_id=target_device_id,
            action=action,
            new_sampling_rate_seconds=float(new_sampling_rate_seconds),
            new_malignancy_threshold=float(new_malignancy_threshold),
            fault_simulation_mode=fault_simulation_mode,
        )
        req = client_gateway_pb2.ClientRequest(
            request_id=f"CTRL-{uuid.uuid4().hex[:6]}",
            command=client_gateway_pb2.CMD_SEND_DEVICE_CONTROL,
            target_device_id=target_device_id,
            device_config=cfg_req,
        )
        try:
            resp = self._send_request(req)
            if resp.status == client_gateway_pb2.STATUS_OK:
                return True, resp.config_response, resp.message
            return False, resp.config_response, resp.message
        except Exception as e:
            empty_resp = device_control_pb2.DeviceConfigResponse(success=False, message=str(e))
            return False, empty_resp, str(e)

    def query_analytics(
        self,
        query_type: client_gateway_pb2.AnalyticsType,
        time_window_seconds: int = 3600,
    ) -> Tuple[bool, Optional[client_gateway_pb2.AnalyticsResponse], str]:
        """Executa uma das 3 consultas analíticas agregadas no Gateway."""
        req = client_gateway_pb2.ClientRequest(
            request_id=f"QUERY-{uuid.uuid4().hex[:6]}",
            command=client_gateway_pb2.CMD_ANALYTICS_QUERY,
            analytics_query=client_gateway_pb2.AnalyticsQueryRequest(
                query_type=query_type,
                time_window_seconds=time_window_seconds,
            ),
        )
        try:
            resp = self._send_request(req)
            if resp.status == client_gateway_pb2.STATUS_OK:
                return True, resp.analytics, resp.message
            return False, None, resp.message
        except Exception as e:
            return False, None, str(e)
