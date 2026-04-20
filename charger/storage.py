"""
数据存储模块 - SQLite
负责充电功率数据的持久化存储和查询。
"""

import sqlite3
import os
import json
from datetime import datetime
from typing import Optional, List, Dict, Any


class ChargeDatabase:
    """充电数据数据库管理类"""

    def __init__(self, db_path: str = "./output/data/charge_data.db"):
        """
        初始化数据库连接，自动建表。

        Args:
            db_path: 数据库文件路径，目录不存在会自动创建
        """
        # 确保目录存在
        db_dir = os.path.dirname(db_path)
        if db_dir and not os.path.exists(db_dir):
            os.makedirs(db_dir, exist_ok=True)

        self.db_path = db_path
        self.conn = sqlite3.connect(db_path)
        self.conn.row_factory = sqlite3.Row  # 查询结果可用列名访问
        self._create_tables()

    def _create_tables(self):
        """创建数据表（如果不存在）"""
        self.conn.executescript("""
            CREATE TABLE IF NOT EXISTS charge_records (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp TEXT NOT NULL,
                power_watts REAL,
                energy_kwh REAL,
                order_id TEXT,
                raw_data TEXT,
                collector_mode TEXT,
                created_at TEXT DEFAULT (datetime('now', 'localtime'))
            );

            CREATE INDEX IF NOT EXISTS idx_timestamp ON charge_records(timestamp);
            CREATE INDEX IF NOT EXISTS idx_order_id ON charge_records(order_id);

            CREATE TABLE IF NOT EXISTS charge_sessions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                order_id TEXT UNIQUE NOT NULL,
                start_time TEXT,
                end_time TEXT,
                max_power REAL,
                min_power REAL,
                avg_power REAL,
                total_records INTEGER DEFAULT 0,
                status TEXT DEFAULT 'active'
            );
        """)
        self.conn.commit()

    def insert_record(
        self,
        power_watts: float,
        order_id: Optional[str] = None,
        raw_data: Optional[Dict] = None,
        collector_mode: str = "requests",
        energy_kwh: Optional[float] = None,
        timestamp: Optional[str] = None
    ) -> int:
        """
        插入一条充电记录。

        Args:
            power_watts: 充电功率（瓦特）
            order_id: 充电订单ID（可选）
            raw_data: 原始响应数据（可选，会序列化为 JSON 存储）
            collector_mode: 采集模式标识
            energy_kwh: 已充电量（度电 kWh）
            timestamp: 时间戳（可选，不传则使用当前系统时间）

        Returns:
            插入记录的 ID
        """
        if not timestamp:
            timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        raw_json = json.dumps(raw_data, ensure_ascii=False) if raw_data else None

        cursor = self.conn.execute(
            """INSERT INTO charge_records
               (timestamp, power_watts, energy_kwh, order_id, raw_data, collector_mode)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (timestamp, power_watts, energy_kwh, order_id, raw_json, collector_mode)
        )
        self.conn.commit()

        # 更新会话信息
        if order_id:
            self._update_session(order_id, power_watts)

        return cursor.lastrowid

    def _update_session(self, order_id: str, power_watts: float):
        """更新或创建充电会话统计"""
        existing = self.conn.execute(
            "SELECT * FROM charge_sessions WHERE order_id = ?", (order_id,)
        ).fetchone()

        if existing:
            # 更新现有会话
            self.conn.execute(
                """UPDATE charge_sessions SET
                   max_power = MAX(max_power, ?),
                   min_power = MIN(min_power, ?),
                   avg_power = (avg_power * total_records + ?) / (total_records + 1),
                   total_records = total_records + 1
                   WHERE order_id = ?""",
                (power_watts, power_watts, power_watts, order_id)
            )
        else:
            # 创建新会话
            self.conn.execute(
                """INSERT INTO charge_sessions
                   (order_id, start_time, max_power, min_power, avg_power, total_records)
                   VALUES (?, datetime('now', 'localtime'), ?, ?, ?, 1)""",
                (order_id, power_watts, power_watts, power_watts)
            )
        self.conn.commit()

    def query_records(
        self,
        order_id: Optional[str] = None,
        start_time: Optional[str] = None,
        end_time: Optional[str] = None,
        limit: int = 1000
    ) -> List[Dict[str, Any]]:
        """
        查询充电记录。

        Args:
            order_id: 按订单ID筛选（可选）
            start_time: 起始时间，格式 "YYYY-MM-DD HH:MM:SS"（可选）
            end_time: 结束时间（可选）
            limit: 最大返回条数

        Returns:
            记录列表，每条记录为字典
        """
        query = "SELECT * FROM charge_records WHERE 1=1"
        params = []

        if order_id:
            query += " AND order_id = ?"
            params.append(order_id)
        if start_time:
            query += " AND timestamp >= ?"
            params.append(start_time)
        if end_time:
            query += " AND timestamp <= ?"
            params.append(end_time)

        query += " ORDER BY timestamp ASC LIMIT ?"
        params.append(limit)

        rows = self.conn.execute(query, params).fetchall()
        return [dict(row) for row in rows]

    def get_latest_record(self, order_id: Optional[str] = None) -> Optional[Dict]:
        """获取最新一条记录"""
        query = "SELECT * FROM charge_records"
        params = []
        if order_id:
            query += " WHERE order_id = ?"
            params.append(order_id)
        query += " ORDER BY id DESC LIMIT 1"

        row = self.conn.execute(query, params).fetchone()
        return dict(row) if row else None

    def get_sessions_summary(self) -> List[Dict]:
        """获取所有充电会话的汇总信息"""
        rows = self.conn.execute(
            """SELECT * FROM charge_sessions ORDER BY start_time DESC"""
        ).fetchall()
        return [dict(row) for row in rows]

    def export_to_csv(self, output_path: str, order_id: Optional[str] = None):
        """
        导出数据为 CSV 文件。

        Args:
            output_path: CSV 文件输出路径
            order_id: 按订单ID筛选（可选）
        """
        import csv

        records = self.query_records(order_id=order_id, limit=100000)
        if not records:
            print("没有可导出的数据")
            return

        # 确保目录存在
        output_dir = os.path.dirname(output_path)
        if output_dir and not os.path.exists(output_dir):
            os.makedirs(output_dir, exist_ok=True)

        with open(output_path, "w", newline="", encoding="utf-8-sig") as f:
            writer = csv.DictWriter(f, fieldnames=records[0].keys())
            writer.writeheader()
            writer.writerows(records)

        print(f"已导出 {len(records)} 条记录到 {output_path}")

    def close(self):
        """关闭数据库连接"""
        self.conn.close()

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()
