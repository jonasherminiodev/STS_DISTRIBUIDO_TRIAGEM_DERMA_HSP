#!/usr/bin/env python3
"""
Utilitário para inicialização das Fontes de Dados.
Pode iniciar uma fonte individual (--source 1|2|3) ou todas simultaneamente.
"""
import argparse
import os
import sys
import time

_BASE_DIR = os.path.dirname(os.path.abspath(__file__))
if _BASE_DIR not in sys.path:
    sys.path.insert(0, _BASE_DIR)

from sources import DermatoscopySource, UvChamberSource, PatchSensorSource


def main():
    parser = argparse.ArgumentParser(description="Inicializador das Fontes de Dados Distribuídas")
    parser.add_argument("--source", choices=["1", "2", "3", "all"], default="all",
                        help="Fonte a iniciar: 1 (Dermatoscópio gRPC), 2 (Câmara UV), 3 (Patch Dérmico), all (Todas)")
    parser.add_argument("--gateway-host", default="127.0.0.1", help="Host do Gateway (default: 127.0.0.1)")
    parser.add_argument("--gateway-port", type=int, default=9000, help="Porta UDP de telemetria do Gateway (default: 9000)")
    parser.add_argument("--grpc-port", type=int, default=50051, help="Porta gRPC para a Fonte 1 (default: 50051)")
    parser.add_argument("--simulate-ai", action="store_true", help="Força a Fonte 1 a usar o modo de simulação estatística (sem carregar o modelo Keras tcc.h5)")
    parser.add_argument("--trigger-alert", action="store_true", help="Se Fonte 3, dispara um alerta crítico imediato")

    args = parser.parse_args()

    sources = []

    if args.source in ("1", "all"):
        print(f"[+] Iniciando Fonte 1: Estação de Dermatoscopia Digital (gRPC porta {args.grpc_port})...")
        s1 = DermatoscopySource(
            device_id="DERMATOSCOPY-01",
            grpc_port=args.grpc_port,
            gateway_host=args.gateway_host,
            gateway_telemetry_port=args.gateway_port,
            sampling_rate_seconds=4.0,
            force_simulation=args.simulate_ai,
        )
        s1.start()
        sources.append(s1)

    if args.source in ("2", "all"):
        print("[+] Iniciando Fonte 2: Sensor de Cabine UV / Fototerapia (Não Controlável)...")
        s2 = UvChamberSource(
            device_id="UV-CHAMBER-01",
            gateway_host=args.gateway_host,
            gateway_telemetry_port=args.gateway_port,
            sampling_rate_seconds=5.0,
        )
        s2.start()
        sources.append(s2)

    if args.source in ("3", "all"):
        print("[+] Iniciando Fonte 3: Patch Dérmico Conectado (Alerta Imediato)...")
        s3 = PatchSensorSource(
            device_id="PATCH-01",
            gateway_host=args.gateway_host,
            gateway_telemetry_port=args.gateway_port,
            sampling_rate_seconds=5.0,
        )
        s3.start()
        sources.append(s3)

        if args.trigger_alert:
            time.sleep(1.0)
            s3.trigger_critical_event(39.8, "HIPERTERMIA_LOCAL_CRITICA")

    print(f"\n[✓] {len(sources)} fonte(s) em execução! Pressione Ctrl+C para encerrar.\n")

    try:
        while True:
            time.sleep(1.0)
    except KeyboardInterrupt:
        print("\n[!] Encerrando fontes de dados...")
        for s in sources:
            s.stop()
        print("[✓] Fontes finalizadas.")


if __name__ == "__main__":
    main()
