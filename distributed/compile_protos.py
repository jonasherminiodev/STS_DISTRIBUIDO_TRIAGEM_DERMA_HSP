#!/usr/bin/env python3
"""
Script de compilação reproduzível para os arquivos Protocol Buffers (.proto).
Usa o compilador protoc nativo ou grpc_tools para gerar os arquivos Python em distributed/generated.
"""
import os
import subprocess
import sys

def main():
    base_dir = os.path.dirname(os.path.abspath(__file__))
    protos_dir = os.path.join(base_dir, "protos")
    output_dir = os.path.join(base_dir, "generated")

    os.makedirs(output_dir, exist_ok=True)

    proto_files = [
        os.path.join(protos_dir, f)
        for f in os.listdir(protos_dir)
        if f.endswith(".proto")
    ]

    print(f"[+] Compilando {len(proto_files)} arquivos .proto de {protos_dir}...")

    # Tenta usar protoc no PATH
    protoc_bin = "/opt/homebrew/bin/protoc"
    if not os.path.exists(protoc_bin):
        import shutil
        protoc_bin = shutil.which("protoc")

    if not protoc_bin:
        print("[!] Erro: protoc não encontrado no sistema.")
        sys.exit(1)

    cmd = [
        protoc_bin,
        f"-I={protos_dir}",
        f"--python_out={output_dir}",
    ] + proto_files

    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        print(f"[!] Erro na compilação protoc:\n{result.stderr}")
        sys.exit(result.returncode)

    print(f"[✓] Compilação protoc concluída com sucesso em {output_dir}")

if __name__ == "__main__":
    main()
