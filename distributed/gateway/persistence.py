"""
Módulo de Persistência de Dados em SQLite para o Gateway (Pontuação Extra Bônus).
Armazena histórico de leituras de telemetria e incidentes para consultas temporais.
"""
import json
import os
import sqlite3
import threading
import time
from typing import List, Optional

from google.protobuf.json_format import MessageToJson
from generated import common_pb2, telemetry_pb2


class GatewayStorage:
    """Gerenciador de persistência SQLite thread-safe."""

    def __init__(self, db_path: Optional[str] = None):
        if db_path is None:
            base_dir = os.path.dirname(os.path.abspath(__file__))
            db_path = os.path.join(base_dir, "telemetry_history.db")
        self.db_path = db_path
        self._lock = threading.Lock()
        self._init_db()

    def _init_db(self):
        with self._lock:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS telemetry_records (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    device_id TEXT NOT NULL,
                    device_type INTEGER NOT NULL,
                    timestamp_utc INTEGER NOT NULL,
                    sequence_number INTEGER NOT NULL,
                    is_immediate_alert INTEGER NOT NULL,
                    payload_type TEXT NOT NULL,
                    payload_json TEXT NOT NULL
                )
            """)
            cursor.execute("""
                CREATE INDEX IF NOT EXISTS idx_telemetry_device 
                ON telemetry_records (device_id, timestamp_utc)
            """)
            cursor.execute("""
                CREATE INDEX IF NOT EXISTS idx_telemetry_time 
                ON telemetry_records (timestamp_utc)
            """)
            conn.commit()
            conn.close()

    def store_telemetry(self, msg: telemetry_pb2.TelemetryMessage):
        """Grava uma mensagem de telemetria no banco de dados SQLite."""
        payload_type = msg.WhichOneof("payload") or "unknown"
        json_str = MessageToJson(msg)

        with self._lock:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO telemetry_records (
                    device_id, device_type, timestamp_utc, sequence_number,
                    is_immediate_alert, payload_type, payload_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
            """, (
                msg.header.device_id,
                int(msg.header.device_type),
                int(msg.header.timestamp_utc or time.time()),
                int(msg.header.sequence_number),
                1 if msg.is_immediate_alert else 0,
                payload_type,
                json_str,
            ))
            conn.commit()
            conn.close()

    def get_recent_count(self) -> int:
        """Retorna o total de registros salvos."""
        with self._lock:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            cursor.execute("SELECT COUNT(*) FROM telemetry_records")
            count = cursor.fetchone()[0]
            conn.close()
            return count
