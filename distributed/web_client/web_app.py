"""
Cliente com Interface Gráfica Web (Pontuação Extra Bônus).
Aplicação Flask que atua como cliente TCP do Gateway Central, exibindo séries temporais
com Chart.js e painel de controle de dispositivos.
"""
import argparse
import os
import sys

_DISTRIBUTED_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_WORKSPACE_ROOT = os.path.dirname(_DISTRIBUTED_DIR)
_VENV_PACKAGES = os.path.join(_WORKSPACE_ROOT, "ANALISE_IMG_CANCER_DE_PELE ", ".venv", "lib", "python3.9", "site-packages")

if os.path.exists(_VENV_PACKAGES) and _VENV_PACKAGES not in sys.path:
    sys.path.insert(0, _VENV_PACKAGES)
if _DISTRIBUTED_DIR not in sys.path:
    sys.path.insert(0, _DISTRIBUTED_DIR)

from flask import Flask, jsonify, render_template, request

from generated import common_pb2, device_control_pb2, client_gateway_pb2
from client.tcp_gateway_client import TCPGatewayClient

TYPE_LABELS = {
    common_pb2.DERMATOSCOPY_AI: "Dermatoscópio com IA (Controlável)",
    common_pb2.UV_CHAMBER: "Câmara UV / Fototerapia (Não Controlável)",
    common_pb2.PATCH_SENSOR: "Patch Dérmico (Alerta Imediato)",
}

app = Flask(
    __name__,
    template_folder=os.path.join(os.path.dirname(os.path.abspath(__file__)), "templates")
)

# Instância padrão do cliente TCP com o Gateway
gateway_client = TCPGatewayClient(host="127.0.0.1", port=8000)


@app.route("/")
def index():
    """Renderiza a página principal do Dashboard Clínico."""
    return render_template("dashboard.html")


@app.route("/api/devices")
def api_devices():
    """Consulta fontes conectadas no Gateway via socket TCP."""
    ok, devices, msg = gateway_client.list_devices()
    result = []
    for d in devices:
        result.append({
            "device_id": d.device_id,
            "device_type": d.device_type,
            "device_type_name": TYPE_LABELS.get(d.device_type, "Outro"),
            "ip_address": d.ip_address,
            "grpc_port": d.grpc_port,
            "state": d.state,
            "total_telemetry_count": d.total_telemetry_count,
            "immediate_alert_count": d.immediate_alert_count,
        })
    return jsonify({"success": ok, "devices": result, "message": msg})


@app.route("/api/analytics/<int:query_id>")
def api_analytics(query_id: int):
    """Executa consultas analíticas agregadas via socket TCP."""
    q_map = {
        1: client_gateway_pb2.QUERY_1_MALIGNANCY_SUMMARY,
        2: client_gateway_pb2.QUERY_2_UV_CLIMATE_SUMMARY,
        3: client_gateway_pb2.QUERY_3_DEVICE_INCIDENTS_SUMMARY,
    }
    if query_id not in q_map:
        return jsonify({"success": False, "message": "ID de consulta inválido"}), 400

    ok, resp, msg = gateway_client.query_analytics(q_map[query_id], time_window_seconds=3600)
    if not ok or not resp:
        return jsonify({"success": False, "message": msg}), 500

    data = {"success": True}
    if query_id == 1:
        mal = resp.malignancy
        data["malignancy"] = {
            "total_screenings": mal.total_screenings,
            "malignant_count": mal.malignant_count,
            "malignancy_rate": mal.malignancy_rate,
            "avg_confidence": mal.avg_confidence,
            "class_distribution": dict(mal.class_distribution),
        }
    elif query_id == 2:
        uv = resp.uv_climate
        data["uv_climate"] = {
            "total_samples": uv.total_samples,
            "avg_uva": uv.avg_uva,
            "std_dev_uva": uv.std_dev_uva,
            "avg_uvb": uv.avg_uvb,
            "std_dev_uvb": uv.std_dev_uvb,
            "avg_temperature": uv.avg_temperature,
            "std_dev_temperature": uv.std_dev_temperature,
            "avg_humidity": uv.avg_humidity,
            "std_dev_humidity": uv.std_dev_humidity,
        }
    elif query_id == 3:
        inc = resp.incidents
        devices_ranked = []
        for r in inc.devices_ranked:
            devices_ranked.append({
                "device_id": r.device_id,
                "device_type": r.device_type,
                "immediate_alert_count": r.immediate_alert_count,
                "error_state_count": r.error_state_count,
                "last_incident_description": r.last_incident_description,
            })
        data["incidents"] = {
            "most_unstable_device_id": inc.most_unstable_device_id,
            "devices_ranked": devices_ranked,
        }

    return jsonify(data)


@app.route("/api/control", methods=["POST"])
def api_control():
    """Despacha comando de controle remoto para fonte controlável via Gateway/gRPC."""
    body = request.get_json() or {}
    device_id = body.get("device_id", "DERMATOSCOPY-01")
    action_str = body.get("action", "ACTIVATE")
    rate = float(body.get("sampling_rate", 0.0))
    thresh = float(body.get("threshold", 0.0))

    act_map = {
        "ACTIVATE": device_control_pb2.ACTIVATE,
        "DEACTIVATE": device_control_pb2.DEACTIVATE,
        "SET_SAMPLING_RATE": device_control_pb2.SET_SAMPLING_RATE,
        "SET_ALERT_THRESHOLD": device_control_pb2.SET_ALERT_THRESHOLD,
        "SIMULATE_FAULT": device_control_pb2.SIMULATE_FAULT,
        "RESET": device_control_pb2.RESET,
    }
    action = act_map.get(action_str, device_control_pb2.ACTION_UNSPECIFIED)

    ok, cfg_resp, err_msg = gateway_client.send_device_control(
        target_device_id=device_id,
        action=action,
        new_sampling_rate_seconds=rate,
        new_malignancy_threshold=thresh,
        fault_simulation_mode="DASHBOARD_FAULT_SIMULATION",
    )

    return jsonify({
        "success": ok and cfg_resp.success,
        "message": cfg_resp.message or err_msg,
        "current_state": cfg_resp.current_state,
    })


def main():
    parser = argparse.ArgumentParser(description="Cliente Web Dashboard (Bônus)")
    parser.add_argument("--port", type=int, default=5050, help="Porta HTTP do Dashboard")
    parser.add_argument("--gateway-port", type=int, default=8000, help="Porta TCP do Gateway")
    parser.add_argument("--gateway-host", default="127.0.0.1", help="Host TCP do Gateway")

    args = parser.parse_args()

    global gateway_client
    gateway_client = TCPGatewayClient(host=args.gateway_host, port=args.gateway_port)

    print(f"[+] Iniciando Dashboard Web em http://127.0.0.1:{args.port}...")
    print(f"[+] Conectando ao Gateway TCP em {args.gateway_host}:{args.gateway_port}")
    app.run(host="0.0.0.0", port=args.port, debug=False)


if __name__ == "__main__":
    main()
