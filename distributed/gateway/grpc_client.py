"""
Cliente gRPC do Gateway para envio de comandos às fontes controláveis.
Consulta a tabela de dispositivos para obter o IP e a porta gRPC da fonte alvo.
"""
from typing import Optional, Tuple
import grpc

from generated import common_pb2, device_control_pb2, device_control_pb2_grpc
from .device_registry import DeviceRegistry


class GatewayGRPCController:
    """Despacha chamadas RPC de controle para as fontes controláveis."""

    def __init__(self, registry: DeviceRegistry, timeout_seconds: float = 3.0):
        self.registry = registry
        self.timeout_seconds = timeout_seconds

    def send_config_command(
        self,
        target_device_id: str,
        config_request: device_control_pb2.DeviceConfigRequest,
    ) -> Tuple[bool, device_control_pb2.DeviceConfigResponse]:
        """Encaminha requisição de configuração gRPC para a fonte especificada."""
        dev = self.registry.get_device(target_device_id)
        if not dev:
            return False, device_control_pb2.DeviceConfigResponse(
                success=False,
                message=f"Dispositivo '{target_device_id}' não encontrado no Gateway.",
                current_state=common_pb2.STATE_UNSPECIFIED,
            )

        if dev.grpc_port <= 0:
            return False, device_control_pb2.DeviceConfigResponse(
                success=False,
                message=f"Dispositivo '{target_device_id}' é uma fonte contínua não controlável (sem porta gRPC).",
                current_state=dev.state,
            )

        channel_target = f"{dev.ip_address}:{dev.grpc_port}"
        try:
            with grpc.insecure_channel(channel_target) as channel:
                stub = device_control_pb2_grpc.DeviceControlStub(channel)
                response = stub.ConfigureDevice(config_request, timeout=self.timeout_seconds)

                # Atualiza o estado na tabela do Gateway com base na resposta gRPC
                dev.state = response.current_state
                return True, response
        except grpc.RpcError as rpc_err:
            error_msg = f"Falha na comunicação gRPC com '{target_device_id}' ({channel_target}): {rpc_err.details() or rpc_err.code()}"
            dev.state = common_pb2.STATE_ERROR
            return False, device_control_pb2.DeviceConfigResponse(
                success=False,
                message=error_msg,
                current_state=common_pb2.STATE_ERROR,
            )
        except Exception as e:
            return False, device_control_pb2.DeviceConfigResponse(
                success=False,
                message=f"Erro interno ao invocar gRPC: {str(e)}",
                current_state=dev.state,
            )

    def get_remote_device_state(
        self,
        target_device_id: str,
    ) -> Tuple[bool, Optional[device_control_pb2.DeviceStateResponse], str]:
        """Consulta estado detalhado via RPC GetDeviceState."""
        dev = self.registry.get_device(target_device_id)
        if not dev or dev.grpc_port <= 0:
            return False, None, "Dispositivo não encontrado ou não controlável"

        channel_target = f"{dev.ip_address}:{dev.grpc_port}"
        try:
            with grpc.insecure_channel(channel_target) as channel:
                stub = device_control_pb2_grpc.DeviceControlStub(channel)
                resp = stub.GetDeviceState(
                    device_control_pb2.DeviceStateRequest(device_id=target_device_id),
                    timeout=self.timeout_seconds,
                )
                return True, resp, "Sucesso"
        except Exception as e:
            return False, None, str(e)
