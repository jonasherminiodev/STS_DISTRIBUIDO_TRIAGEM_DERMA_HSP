# Generated gRPC code for distributed.DeviceControl
import grpc
try:
    from . import device_control_pb2 as device__control__pb2
except (ImportError, ValueError):
    import device_control_pb2 as device__control__pb2


class DeviceControlStub(object):
    """Cliente gRPC para envio de comandos de controle para fontes controláveis."""

    def __init__(self, channel):
        """Constructor.

        Args:
            channel: A grpc.Channel.
        """
        self.ConfigureDevice = channel.unary_unary(
            '/distributed.DeviceControl/ConfigureDevice',
            request_serializer=device__control__pb2.DeviceConfigRequest.SerializeToString,
            response_deserializer=device__control__pb2.DeviceConfigResponse.FromString,
        )
        self.GetDeviceState = channel.unary_unary(
            '/distributed.DeviceControl/GetDeviceState',
            request_serializer=device__control__pb2.DeviceStateRequest.SerializeToString,
            response_deserializer=device__control__pb2.DeviceStateResponse.FromString,
        )


class DeviceControlServicer(object):
    """Servidor gRPC implementado pelas fontes de dados controláveis."""

    def ConfigureDevice(self, request, context):
        """Ajusta parâmetros de operação (frequência de envio, limiar de alerta, ligar/desligar, simular falha)"""
        context.set_code(grpc.StatusCode.UNIMPLEMENTED)
        context.set_details('Method not implemented!')
        raise NotImplementedError('Method not implemented!')

    def GetDeviceState(self, request, context):
        """Consulta o estado operacional atual da fonte"""
        context.set_code(grpc.StatusCode.UNIMPLEMENTED)
        context.set_details('Method not implemented!')
        raise NotImplementedError('Method not implemented!')


def add_DeviceControlServicer_to_server(servicer, server):
    rpc_method_handlers = {
        'ConfigureDevice': grpc.unary_unary_rpc_method_handler(
            servicer.ConfigureDevice,
            request_deserializer=device__control__pb2.DeviceConfigRequest.FromString,
            response_serializer=device__control__pb2.DeviceConfigResponse.SerializeToString,
        ),
        'GetDeviceState': grpc.unary_unary_rpc_method_handler(
            servicer.GetDeviceState,
            request_deserializer=device__control__pb2.DeviceStateRequest.FromString,
            response_serializer=device__control__pb2.DeviceStateResponse.SerializeToString,
        ),
    }
    generic_handler = grpc.method_handlers_generic_handler(
        'distributed.DeviceControl', rpc_method_handlers
    )
    server.add_generic_rpc_handlers((generic_handler,))
