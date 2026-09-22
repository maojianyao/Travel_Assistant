#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
@File    : trip_store.py
@Time    : 2026/9/22 11:36
@Author  : MaoJian Y
@Desc    : 旅行计划持久化存储(SQLite)
"""
import asyncio
import json
import os.path
import sqlite3
import threading
import uuid
from datetime import datetime
from typing import Optional

from backend.app.config import get_settings
from backend.app.utils.logger import get_logger

logger = get_logger(__name__)

class TripStore:
    """基于SQLite的旅行计划存储，异步入口通过asyncio.to_thread在线程池执行"""

    def __init__(self, db_path: str):
        self._db_path = db_path
        self._conn: Optional[sqlite3.Connection] = None
        self._lock = threading.Lock()

    def initialize(self) -> None:
        """初始化数据库连接与表结构"""
        self._get_conn()

    def _get_conn(self) -> sqlite3.Connection:
        if self._conn is None:
            db_dir = os.path.dirname(self._db_path)
            if db_dir:
                os.makedirs(db_dir, exist_ok=True)
            self._conn = sqlite3.connect(self._db_path, check_same_thread=False)
            # 行结果按列名访问(row["id"]), 缺省返回tuple会导致字符串索引报错
            self._conn.row_factory = sqlite3.Row
            self._conn.execute(
                """
                CREATE TABLE IF NOT EXISTS trips (
                    id            TEXT PRIMARY KEY,
                    city          TEXT NOT NULL,
                    start_date    TEXT NOT NULL,
                    end_date      TEXT NOT NULL,
                    travel_days   INTEGER NOT NULL,
                    request_json  TEXT NOT NULL,
                    plan_json     TEXT NOT NULL,
                    is_fallback   INTEGER NOT NULL DEFAULT 0,
                    created_at    TEXT NOT NULL
                )
                """
            )
            self._conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_trips_created_at ON trips(created_at DESC)"
            )
            self._conn.commit()
            logger.info(f"旅行计划存储已就绪: {self._db_path}")
        return self._conn

    def save_trip(self, request: dict, plan: dict) -> str:
        with self._lock:
            trip_id = uuid.uuid4().hex[:12]
            conn = self._get_conn()
            conn.execute(
                """
                INSERT INTO trips
                    (id, city, start_date, end_date, travel_days,
                     request_json, plan_json, is_fallback, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    trip_id,
                    plan.get("city", ""),
                    plan.get("start_date", ""),
                    plan.get("end_date", ""),
                    len(plan.get("days") or []),
                    json.dumps(request, ensure_ascii=False),
                    json.dumps(plan, ensure_ascii=False),
                    1 if plan.get("is_fallback") else 0,
                    datetime.now().isoformat(timespec="seconds"),
                ),
            )
            conn.commit()
            logger.info(f"旅行计划已保存: trip_id={trip_id}, city={plan.get('city')}")
            return trip_id

    def get_trip(self, trip_id: str) -> Optional[dict]:
        with self._lock:
            row = (
                self._get_conn()
                .execute("SELECT * FROM trips WHERE id = ?", (trip_id,))
                .fetchone()
            )
        if row is None:
            return None
        return {
            "trip_id": row["id"],
            "created_at": row["created_at"],
            "request": json.loads(row["request_json"]),
            "plan": json.loads(row["plan_json"]),
        }

    def list_trips(self, limit: int = 20) -> list[dict]:
        with self._lock:
            rows = (
                self._get_conn()
                .execute(
                    """
                    SELECT id AS trip_id, city, start_date, end_date,
                           travel_days, is_fallback, created_at
                    FROM trips ORDER BY created_at DESC LIMIT ?
                    """,
                    (limit,),
                )
                .fetchall()
            )
        return [dict(row) for row in rows]

    async def save_trip_async(self, request: dict, plan: dict) -> str:
        return await asyncio.to_thread(self.save_trip, request, plan)

    async def get_trip_async(self, trip_id: str) -> Optional[dict]:
        return await asyncio.to_thread(self.get_trip, trip_id)

    async def list_trips_async(self, limit: int = 20) -> list[dict]:
        return await asyncio.to_thread(self.list_trips, limit)

_trip_store: Optional[TripStore] = None

def get_trip_store() -> TripStore:
    """获取旅行计划存储实例(单例)"""
    global _trip_store
    if _trip_store is None:
        _trip_store = TripStore(get_settings().database_path)
    return _trip_store