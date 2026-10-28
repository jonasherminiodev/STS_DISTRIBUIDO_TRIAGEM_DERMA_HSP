"""
Cliente de Linha de Comando (CLI) para Gestão de Ambiente Inteligente.
Processo separado que interage com o Gateway via sockets TCP e Protocol Buffers.
Permite listar fontes, enviar comandos de controle gRPC e executar as 3 consultas analíticas.
"""
import argparse
import os
import sys
import time

_BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _BASE_DIR not in sys.path:
    sys.path.insert(0, _BASE_DIR)

from generated import common_pb2, device_control_pb2, client_gateway_pb2
from client.tcp_gateway_client import TCPGatewayClient

TYPE_NAMES = {
    common_pb2.DERMATOSCOPY_AI: "Dermatoscópio com IA (Controlável)",
    common_pb2.UV_CHAMBER: "Câmara UV / Fototerapia (Não Controlável)",
    common_pb2.PATCH_SENSOR: "Patch Dérmico (Alerta Imediato)",
}

STATE_NAMES = {
    common_pb2.STATE_ACTIVE: "ATIVO (OK)",
    common_pb2.STATE_IDLE: "REPOUSO (IDLE)",
    common_pb2.STATE_DEGRADED: "DEGRADADO",
    common_pb2.STATE_ERROR: "ERRO / FALHA",
    common_pb2.STATE_OFFLINE: "DESCONECTADO (OFFLINE)",
}


def print_banner():
    print("=" * 80)
    print(" SISTEMA DISTRIBUÍDO DE GESTÃO INTELIGENTE PARA TRIAGEM DERMATOLÓGICA")
    print(" Cliente de Monitoramento, Controle e Análise Agregada (via TCP + Protobuf)")
    print("=" * 80)


def format_device_table(devices):
    if not devices:
        print("[!] Nenhuma fonte de dados conectada no momento.")
        return

    print("\n" + "-" * 88)
    print(f"{'ID Dispositivo':<18} | {'Tipo':<30} | {'IP:gRPC':<16} | {'Estado':<12} | {'Msg/Alert'}")
    print("-" * 88)
    for dev in devices:
        t_name = TYPE_NAMES.get(dev.device_type, "Desconhecido")
        s_name = STATE_NAMES.get(dev.state, "INDEFINIDO")
        grpc_str = f"{dev.ip_address}:{dev.grpc_port}" if dev.grpc_port > 0 else f"{dev.ip_address}:-"
        counts = f"{dev.total_telemetry_count} / {dev.immediate_alert_count}"
        print(f"{dev.device_id:<18} | {t_name:<30} | {grpc_str:<16} | {s_name:<12} | {counts}")
    print("-" * 88 + "\n")


def display_analytics_1(malignancy: client_gateway_pb2.MalignancyAnalyticsResult):
    print("\n" + "=" * 65)
    print(" CONSULTA ANALÍTICA 1: RESUMO DE TRIAGEM ONCOLÓGICA (IA)")
    print("=" * 65)
    print(f"Total de exames dermatológicos avaliados: {malignancy.total_screenings}")
    print(f"Total de lesões de alto risco (Malignas): {malignancy.malignant_count}")
    print(f"Taxa de detecção de malignidade:          {malignancy.malignancy_rate:.1%}")
    print(f"Média de confiança do modelo Keras:       {malignancy.avg_confidence:.2%}")
    print("\nDistribuição quantitativa das 7 classes:")
    print("-" * 65)
    for cname, count in sorted(malignancy.class_distribution.items(), key=lambda x: x[1], reverse=True):
        print(f"  * {cname:<48}: {count} caso(s)")
    print("=" * 65 + "\n")


def display_analytics_2(uv: client_gateway_pb2.UvClimateAnalyticsResult):
    print("\n" + "=" * 65)
    print(" CONSULTA ANALÍTICA 2: DOSIMETRIA UV E CLIMA DE SALA")
    print("=" * 65)
    print(f"Total de amostras contínuas coletadas:    {uv.total_samples}")
    print(f"Intensidade UVA média (mW/cm²):           {uv.avg_uva:.3f} (± {uv.std_dev_uva:.3f})")
    print(f"Intensidade UVB média (mW/cm²):           {uv.avg_uvb:.3f} (± {uv.std_dev_uvb:.3f})")
    print(f"Temperatura ambiente média (°C):          {uv.avg_temperature:.2f}°C (± {uv.std_dev_temperature:.2f})")
    print(f"Umidade relativa média (%):               {uv.avg_humidity:.1f}% (± {uv.std_dev_humidity:.1f})")
    print("=" * 65 + "\n")


def display_analytics_3(incidents: client_gateway_pb2.IncidentsAnalyticsResult):
    print("\n" + "=" * 65)
    print(" CONSULTA ANALÍTICA 3: RANKING DE INCIDENTES E INSTABILIDADES")
    print("=" * 65)
    print(f"Dispositivo com maior índice de instabilidade: {incidents.most_unstable_device_id}")
    print("\nRanking de fontes monitoradas:")
    print("-" * 65)
    for idx, item in enumerate(incidents.devices_ranked, 1):
        t_name = TYPE_NAMES.get(item.device_type, "Outro")
        print(f" {idx}. [{item.device_id}] ({t_name})")
        print(f"    - Alertas imediatos disparados: {item.immediate_alert_count}")
        print(f"    - Estados de falha / inativo:   {item.error_state_count}")
        print(f"    - Última anomalia reportada:    {item.last_incident_description}")
    print("=" * 65 + "\n")


def interactive_menu(client: TCPGatewayClient):
    print_banner()

    while True:
        print("\n--- MENU PRINCIPAL ---")
        print("[1] Listar fontes conectadas e estados operacionais")
        print("[2] Enviar comando de controle (gRPC) para fonte controlável")
        print("[3] Executar Consulta 1: Resumo de Triagem de Malignidade (IA)")
        print("[4] Executar Consulta 2: Resumo UV e Clima de Sala de Fototerapia")
        print("[5] Executar Consulta 3: Ranking de Incidentes e Instabilidade")
        print("[6] Sair")

        choice = input("\nEscolha uma opção (1-6): ").strip()

        if choice == "1":
            success, devices, msg = client.list_devices()
            if success:
                format_device_table(devices)
            else:
                print(f"[!] Erro ao listar fontes: {msg}")

        elif choice == "2":
            success, devices, _ = client.list_devices()
            if not success or not devices:
                print("[!] Nenhuma fonte disponível para controle.")
                continue

            controllable = [d for d in devices if d.grpc_port > 0]
            if not controllable:
                print("[!] Nenhuma fonte controlável (com servidor gRPC) foi descoberta ainda.")
                continue

            print("\nFontes controláveis disponíveis:")
            for i, d in enumerate(controllable, 1):
                print(f"  [{i}] {d.device_id} ({d.ip_address}:{d.grpc_port}) - Estado: {STATE_NAMES.get(d.state, 'N/A')}")

            sel = input(f"Selecione a fonte (1-{len(controllable)}): ").strip()
            try:
                sel_idx = int(sel) - 1
                target_dev = controllable[sel_idx]
            except Exception:
                print("[!] Opção inválida.")
                continue

            print("\nComandos suportados:")
            print("  [1] Ativar dispositivo (ACTIVATE)")
            print("  [2] Colocar em repouso (DEACTIVATE)")
            print("  [3] Alterar frequência de envio / amostragem (SET_SAMPLING_RATE)")
            print("  [4] Ajustar limiar de malignidade IA (SET_ALERT_THRESHOLD)")
            print("  [5] Simular falha de sensor ótico (SIMULATE_FAULT)")
            print("  [6] Resetar dispositivo para estado ativo (RESET)")

            cmd_sel = input("Escolha o comando (1-6): ").strip()

            action = device_control_pb2.ACTION_UNSPECIFIED
            sampling_rate = 0.0
            threshold = 0.0
            fault_mode = ""

            if cmd_sel == "1":
                action = device_control_pb2.ACTIVATE
            elif cmd_sel == "2":
                action = device_control_pb2.DEACTIVATE
            elif cmd_sel == "3":
                action = device_control_pb2.SET_SAMPLING_RATE
                val = input("Novo intervalo em segundos (ex: 2.0): ").strip()
                try:
                    sampling_rate = float(val)
                except ValueError:
                    print("[!] Valor inválido.")
                    continue
            elif cmd_sel == "4":
                action = device_control_pb2.SET_ALERT_THRESHOLD
                val = input("Novo limiar de malignidade (0.0 a 1.0, ex: 0.75): ").strip()
                try:
                    threshold = float(val)
                except ValueError:
                    print("[!] Valor inválido.")
                    continue
            elif cmd_sel == "5":
                action = device_control_pb2.SIMULATE_FAULT
                fault_mode = "FALHA_CALIBRACAO_OTICA_LENTE"
            elif cmd_sel == "6":
                action = device_control_pb2.RESET
            else:
                print("[!] Comando inválido.")
                continue

            print(f"\n[+] Enviando comando para {target_dev.device_id} via Gateway TCP -> gRPC...")
            ok, cfg_resp, err_msg = client.send_device_control(
                target_device_id=target_dev.device_id,
                action=action,
                new_sampling_rate_seconds=sampling_rate,
                new_malignancy_threshold=threshold,
                fault_simulation_mode=fault_mode,
            )
            if ok and cfg_resp.success:
                print(f"[✓] Resposta gRPC: {cfg_resp.message} (Estado atual: {STATE_NAMES.get(cfg_resp.current_state, 'N/A')})")
            else:
                print(f"[!] Falha no comando: {err_msg or cfg_resp.message}")

        elif choice == "3":
            ok, resp, msg = client.query_analytics(client_gateway_pb2.QUERY_1_MALIGNANCY_SUMMARY)
            if ok and resp:
                display_analytics_1(resp.malignancy)
            else:
                print(f"[!] Erro na consulta analítica: {msg}")

        elif choice == "4":
            ok, resp, msg = client.query_analytics(client_gateway_pb2.QUERY_2_UV_CLIMATE_SUMMARY)
            if ok and resp:
                display_analytics_2(resp.uv_climate)
            else:
                print(f"[!] Erro na consulta analítica: {msg}")

        elif choice == "5":
            ok, resp, msg = client.query_analytics(client_gateway_pb2.QUERY_3_DEVICE_INCIDENTS_SUMMARY)
            if ok and resp:
                display_analytics_3(resp.incidents)
            else:
                print(f"[!] Erro na consulta analítica: {msg}")

        elif choice == "6":
            print("\nEncerrando Cliente...")
            break
        else:
            print("[!] Opção inválida. Digite de 1 a 6.")


def main():
    parser = argparse.ArgumentParser(description="Cliente de Monitoramento e Controle do Ambiente Inteligente")
    parser.add_argument("--host", default="127.0.0.1", help="Endereço TCP do Gateway")
    parser.add_argument("--port", type=int, default=8000, help="Porta TCP do Gateway")
    parser.add_argument("--list", action="store_true", help="Listar fontes conectadas e sair")
    parser.add_argument("--query", type=int, choices=[1, 2, 3], help="Executar consulta analítica 1, 2 ou 3")
    parser.add_argument("--control-device", type=str, help="ID do dispositivo alvo para controle")
    parser.add_argument("--action", type=str, choices=["ACTIVATE", "DEACTIVATE", "SET_SAMPLING_RATE", "SET_ALERT_THRESHOLD", "SIMULATE_FAULT", "RESET"])
    parser.add_argument("--rate", type=float, default=0.0, help="Taxa de amostragem em segundos")
    parser.add_argument("--threshold", type=float, default=0.0, help="Limiar de malignidade")

    args = parser.parse_args()

    client = TCPGatewayClient(host=args.host, port=args.port)

    # Modo não-interativo via linha de comando
    if args.list:
        ok, devices, msg = client.list_devices()
        if ok:
            format_device_table(devices)
        else:
            print(f"[!] Erro: {msg}")
            sys.exit(1)
        return

    if args.query:
        q_map = {
            1: client_gateway_pb2.QUERY_1_MALIGNANCY_SUMMARY,
            2: client_gateway_pb2.QUERY_2_UV_CLIMATE_SUMMARY,
            3: client_gateway_pb2.QUERY_3_DEVICE_INCIDENTS_SUMMARY,
        }
        ok, resp, msg = client.query_analytics(q_map[args.query])
        if ok and resp:
            if args.query == 1:
                display_analytics_1(resp.malignancy)
            elif args.query == 2:
                display_analytics_2(resp.uv_climate)
            elif args.query == 3:
                display_analytics_3(resp.incidents)
        else:
            print(f"[!] Erro na consulta {args.query}: {msg}")
            sys.exit(1)
        return

    if args.control_device and args.action:
        act_map = {
            "ACTIVATE": device_control_pb2.ACTIVATE,
            "DEACTIVATE": device_control_pb2.DEACTIVATE,
            "SET_SAMPLING_RATE": device_control_pb2.SET_SAMPLING_RATE,
            "SET_ALERT_THRESHOLD": device_control_pb2.SET_ALERT_THRESHOLD,
            "SIMULATE_FAULT": device_control_pb2.SIMULATE_FAULT,
            "RESET": device_control_pb2.RESET,
        }
        ok, cfg_resp, err_msg = client.send_device_control(
            target_device_id=args.control_device,
            action=act_map[args.action],
            new_sampling_rate_seconds=args.rate,
            new_malignancy_threshold=args.threshold,
            fault_simulation_mode="CLI_FAULT_TRIGGER",
        )
        if ok and cfg_resp.success:
            print(f"[✓] Sucesso: {cfg_resp.message} (Estado atual: {STATE_NAMES.get(cfg_resp.current_state, 'N/A')})")
        else:
            print(f"[!] Falha: {err_msg or cfg_resp.message}")
            sys.exit(1)
        return

    # Modo interativo padrão
    interactive_menu(client)


if __name__ == "__main__":
    main()
