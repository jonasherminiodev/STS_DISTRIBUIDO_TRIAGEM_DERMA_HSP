#!/usr/bin/env python3
"""
Ponto de entrada executável para o Gateway Central.
Inicializa o servidor TCP na porta 8000, receptor UDP na porta 9000 e descoberta multicast na porta 10000.
"""
import argparse
import os
import sys
import time

_BASE_DIR = os.path.dirname(os.path.abspath(__file__))
if _BASE_DIR not in sys.path:
    sys.path.insert(0, _BASE_DIR)

from gateway import GatewayServer


def main():
    parser = argparse.ArgumentParser(description="Gateway Central - Ambiente Inteligente de Triagem Dermatológica")
    parser.add_argument("--tcp-port", type=int, default=8000, help="Porta TCP para atendimento ao Cliente (default: 8000)")
    parser.add_argument("--udp-port", type=int, default=9000, help="Porta UDP para recepção de telemetria (default: 9000)")
    parser.add_argument("--multicast-port", type=int, default=10000, help="Porta UDP Multicast de descoberta (default: 10000)")
    parser.add_argument("--discovery-resp-port", type=int, default=10001, help="Porta UDP de resposta de descoberta (default: 10001)")
    parser.add_argument("--timeout", type=float, default=20.0, help="Tempo limite em segundos para marcar fonte como OFFLINE (default: 20s)")

    args = parser.parse_args()

    print("=" * 80)
    print(" GATEWAY CENTRAL - AMBIENTE INTELIGENTE DE TRIAGEM DERMATOLÓGICA")
    print(f" * Sockets TCP Cliente: 0.0.0.0:{args.tcp_port}")
    print(f" * Sockets UDP Telemetria: 0.0.0.0:{args.udp_port}")
    print(f" * Descoberta Multicast: 224.1.1.1:{args.multicast_port} (Respostas: :{args.discovery_resp_port})")
    print(f" * Timeout Heartbeat: {args.timeout}s")
    print("=" * 80)

    gateway = GatewayServer(
        tcp_port=args.tcp_port,
        multicast_group="224.1.1.1",
        multicast_port=args.multicast_port,
        discovery_response_port=args.discovery_resp_port,
        udp_telemetry_port=args.udp_port,
        offline_timeout_seconds=args.timeout,
    )

    try:
        gateway.start()
        print("[✓] Gateway Central em operação! Pressione Ctrl+C para encerrar.\n")
        while True:
            time.sleep(1.0)
    except KeyboardInterrupt:
        print("\n[!] Encerrando Gateway Central...")
        gateway.stop()
        print("[✓] Gateway finalizado com sucesso.")


if __name__ == "__main__":
    main()
