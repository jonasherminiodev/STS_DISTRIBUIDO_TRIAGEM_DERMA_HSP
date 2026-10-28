"""
Módulo gerado contendo as classes Protocol Buffers e gRPC do sistema distribuído.
"""
import sys
import types
import os

# Adiciona retrocompatibilidade com versões de protobuf anteriores a 5.x
if 'google.protobuf.runtime_version' not in sys.modules:
    rv = types.ModuleType('google.protobuf.runtime_version')
    class Domain:
        PUBLIC = 1
    rv.Domain = Domain
    rv.ValidateProtobufRuntimeVersion = lambda *args, **kwargs: None
    sys.modules['google.protobuf.runtime_version'] = rv
    try:
        import google.protobuf
        google.protobuf.runtime_version = rv
    except ImportError:
        pass

# Adiciona o próprio diretório ao sys.path para garantir que imports internos funcionem
_CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
if _CURRENT_DIR not in sys.path:
    sys.path.insert(0, _CURRENT_DIR)

from . import common_pb2
from . import discovery_pb2
from . import telemetry_pb2
from . import device_control_pb2
from . import device_control_pb2_grpc
from . import client_gateway_pb2

__all__ = [
    'common_pb2',
    'discovery_pb2',
    'telemetry_pb2',
    'device_control_pb2',
    'device_control_pb2_grpc',
    'client_gateway_pb2',
]
