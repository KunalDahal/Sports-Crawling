from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from pymongo import MongoClient, DESCENDING
from pymongo.collection import Collection

from .config import Config
from .constants import PIRACY_SCORE_THRESHOLD

class Database:
    def __init__(self, cfg: Config) -> None:
        self._client = MongoClient(cfg.mongo_uri)
        self._db     = self._client[cfg.db_name]

    # ── Internal helpers ───────────────────────────────────────────────────
    def _col(self, name: str) -> Collection:
        c = self._db[name]
        c.create_index("url", background=True)
        c.create_index([("score", DESCENDING)], background=True)
        return c

    @staticmethod
    def _now() -> str:
        return datetime.now(timezone.utc).isoformat()

    # ── Sessions ───────────────────────────────────────────────────────────
    def create_session(self, keyword: str) -> str:
        doc = {
            "keyword":       keyword,
            "status":        "running",
            "started_at":    self._now(),
            "finished_at":   None,
            "streams_found": 0,
            "pages_crawled": 0,
            "flagged_count": 0,
        }
        result = self._db["sessions"].insert_one(doc)
        return str(result.inserted_id)

    def update_session(self, session_id: str, **fields) -> None:
        from bson import ObjectId
        self._db["sessions"].update_one(
            {"_id": ObjectId(session_id)},
            {"$set": fields},
        )

    def finish_session(self, session_id: str, streams_found: int = 0) -> None:
        self.update_session(
            session_id,
            status        = "done",
            finished_at   = self._now(),
            streams_found = streams_found,
        )

    def get_session(self, session_id: str) -> dict | None:
        from bson import ObjectId
        doc = self._db["sessions"].find_one({"_id": ObjectId(session_id)})
        if doc:
            doc["_id"] = str(doc["_id"])
        return doc

    def list_sessions(self, limit: int = 20) -> list[dict]:
        docs = list(
            self._db["sessions"]
            .find(
                {},
                {"_id": 1, "keyword": 1, "status": 1, "started_at": 1,
                 "streams_found": 1, "pages_crawled": 1, "flagged_count": 1},
            )
            .sort("started_at", DESCENDING)
            .limit(limit)
        )
        for d in docs:
            d["_id"] = str(d["_id"])
        return docs

    # ── Page / node tree ──────────────────────────────────────────────────
    def upsert_node(self, session_id: str, node: dict) -> None:
        col = self._col(f"pages_{session_id}")
        col.replace_one({"url": node["url"]}, node, upsert=True)

        flagged_count = col.count_documents({"score": {"$gte": PIRACY_SCORE_THRESHOLD}})
        pages_crawled = col.count_documents({})
        self.update_session(
            session_id,
            pages_crawled = pages_crawled,
            flagged_count = flagged_count,
        )

    def get_all_pages(self, session_id: str) -> list[dict]:
        return list(self._col(f"pages_{session_id}").find({}, {"_id": 0}))

    def get_flagged_pages(self, session_id: str) -> list[dict]:
        return list(
            self._col(f"pages_{session_id}")
            .find({"score": {"$gte": PIRACY_SCORE_THRESHOLD}}, {"_id": 0})
            .sort("score", DESCENDING)
        )

    def get_recent_pages(self, session_id: str, limit: int = 50) -> list[dict]:
        return list(
            self._col(f"pages_{session_id}")
            .find({}, {"_id": 0})
            .sort("crawled_at", DESCENDING)
            .limit(limit)
        )

    # ── Streams ───────────────────────────────────────────────────────────
    def record_stream(
        self,
        session_id:  str,
        stream_url:  str,
        source_url:  str,
        keyword:     str,
        stream_type: str = "unknown",
        score:       int = 0,
    ) -> str:
        col = self._db["streams"]
        col.create_index(
            [("session_id", 1), ("stream_url", 1)],
            unique     = True,
            background = True,
        )
        doc = {
            "session_id":    session_id,
            "keyword":       keyword,
            "stream_url":    stream_url,
            "source_url":    source_url,
            "stream_type":   stream_type,
            "score":         score,
            "discovered_at": self._now(),
        }
        try:
            result = col.insert_one(doc)
            from bson import ObjectId
            self._db["sessions"].update_one(
                {"_id": ObjectId(session_id)},
                {"$inc": {"streams_found": 1}},
            )
            return str(result.inserted_id)
        except Exception:
            existing = col.find_one(
                {"session_id": session_id, "stream_url": stream_url},
                {"_id": 1},
            )
            return str(existing["_id"]) if existing else ""

    def get_streams(self, session_id: str) -> list[dict]:
        return list(
            self._db["streams"]
            .find({"session_id": session_id}, {"_id": 0})
            .sort("discovered_at", DESCENDING)
        )

    def get_all_streams(self, limit: int = 100) -> list[dict]:
        return list(
            self._db["streams"]
            .find({}, {"_id": 0})
            .sort("discovered_at", DESCENDING)
            .limit(limit)
        )

    # ── Logs ──────────────────────────────────────────────────────────────
    def log(self, session_id: str, level: str, message: str) -> None:
        self._db["logs"].insert_one({
            "session_id": session_id,
            "level":      level,
            "message":    message,
            "ts":         self._now(),
        })

    def get_logs(
        self,
        session_id: str,
        since_ts:   str | None = None,
        limit:      int        = 100,
    ) -> list[dict]:
        query: dict[str, Any] = {"session_id": session_id}
        if since_ts:
            query["ts"] = {"$gt": since_ts}
        return list(
            self._db["logs"]
            .find(query, {"_id": 0})
            .sort("ts", 1)
            .limit(limit)
        )

    def close(self) -> None:
        self._client.close()