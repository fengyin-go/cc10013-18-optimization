"""缓存命中数据集业务规则：按缓存键模板归并的命中读取、版本化回源刷新与失效捕获。

口径约定（状态流转只允许在本模块改）：
- 每个真实缓存条目在数据集里只有一行，读取按缓存键归并，同一缓存键只暴露一个可见刷新结果；
- 命中量、失效量只随真实缓存条目事件累计，列表、看板、概览等读取路径一律只读，
  不随页面刷新或重复点击变化；
- 回源刷新携带版本戳：刷新途中映射版本发生变化即形成冲突，按「新版本优先」处理——
  旧刷新结果直接丢弃、不得写回覆盖新版本，失效记录落入缓存监控待处理区；
- 两个版本不能混在同一键下：可见结果始终完整属于某一个版本。
"""
from __future__ import annotations

from typing import Any

from app.store import store

MODULE = "cachehit"
MONITOR_MODULE = "monitor"
REQUIRED_FIELDS = ["记录编号", "缓存键模板", "缓存键"]
REFRESHING = "刷新中"
IDLE = "空闲"


def _next_id(rows: list[dict[str, Any]]) -> int:
    return max((int(row.get("id", 0)) for row in rows), default=0) + 1


def _as_int(value: Any) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return 0


class CacheHitService:
    """缓存命中数据集的归并读取与版本化刷新。"""

    # ------------------------------------------------------------------ 读取
    def _merged_rows(self) -> list[dict[str, Any]]:
        """按缓存键归并：同一缓存键只保留一个可见结果，冲突时新版本优先。"""
        merged: dict[str, dict[str, Any]] = {}
        for row in store.rows(MODULE):
            key = str(row.get("缓存键", ""))
            current = merged.get(key)
            if current is None or _as_int(row.get("可见版本")) >= _as_int(current.get("可见版本")):
                merged[key] = row
        return list(merged.values())

    def list_entries(
        self,
        *,
        keyword: str | None = None,
        template: str | None = None,
        page: int = 1,
        size: int = 20,
    ) -> tuple[list[dict[str, Any]], int]:
        """稳定读取：只过滤与分页，不改任何计数，重复点击结果一致。"""
        rows = self._merged_rows()
        if keyword:
            rows = [row for row in rows if keyword in str(row.get("记录编号", ""))]
        if template:
            rows = [row for row in rows if template in str(row.get("缓存键模板", ""))]
        total = len(rows)
        start = max(page - 1, 0) * size
        return rows[start:start + size], total

    def get_entry(self, entry_id: int) -> dict[str, Any] | None:
        return store.find(MODULE, entry_id)

    # ------------------------------------------------------------------ 命中累计
    def record_hit(self, values: dict[str, Any]) -> tuple[dict[str, Any] | None, str]:
        """真实缓存条目的命中事件：唯一会累计命中次数的入口，按条目累计而非页面刷新。"""
        cache_key = str(values.get("缓存键") or "").strip()
        template = str(values.get("缓存键模板") or "").strip()
        if not cache_key or not template:
            return None, "缺少必填字段：缓存键模板、缓存键"
        row = self._find_by_key(cache_key)
        if row is None:
            version = _as_int(values.get("映射版本")) or 1
            row = {
                "id": _next_id(store.rows(MODULE)),
                "status": "已启用",
                "pending": False,
                "abnormal": False,
                "记录编号": f"HIT-{_next_id(store.rows(MODULE)):04d}",
                "缓存键模板": template,
                "缓存键": cache_key,
                "关联端点": str(values.get("关联端点") or ""),
                "映射版本": version,
                "可见版本": version,
                "刷新版本": None,
                "刷新状态": IDLE,
                "命中次数": 0,
                "失效次数": 0,
                "最近失效原因": "",
            }
            store.rows(MODULE).append(row)
        row["命中次数"] = _as_int(row.get("命中次数")) + 1
        return row, f"缓存键 {cache_key} 命中已按真实条目累计"

    # ------------------------------------------------------------------ 回源刷新
    def start_refresh(self, entry_id: int) -> tuple[dict[str, Any] | None, str]:
        """开始一次回源刷新：盖上当前映射版本的版本戳，同键同时只允许一个进行中刷新。"""
        entry = self.get_entry(entry_id)
        if entry is None:
            return None, f"缓存命中记录 {entry_id} 不存在或已归档"
        if entry.get("刷新状态") == REFRESHING:
            return None, "同一缓存键已有一个进行中的刷新，完成前不会再产生第二个可见刷新结果"
        entry["刷新版本"] = _as_int(entry.get("映射版本"))
        entry["刷新状态"] = REFRESHING
        entry["pending"] = True
        return entry, f"缓存键 {entry.get('缓存键')} 开始回源刷新，版本戳 v{entry['刷新版本']}"

    def complete_refresh(self, entry_id: int) -> tuple[dict[str, Any] | None, str]:
        """完成刷新：旧请求完成时不得覆盖新版本；冲突结果按新版本优先丢弃并落监控待处理区。"""
        entry = self.get_entry(entry_id)
        if entry is None:
            return None, f"缓存命中记录 {entry_id} 不存在或已归档"
        if entry.get("刷新状态") != REFRESHING:
            return None, "该缓存键当前没有进行中的刷新，无法完成写回"
        refresh_version = _as_int(entry.get("刷新版本"))
        current_version = _as_int(entry.get("映射版本"))
        entry["刷新状态"] = IDLE
        entry["刷新版本"] = None
        if refresh_version < current_version:
            # 刷新途中映射版本发生变化，形成冲突：新版本优先，旧响应不得写回。
            entry["abnormal"] = True
            entry["pending"] = True
            entry["失效次数"] = _as_int(entry.get("失效次数")) + 1
            reason = (
                f"刷新基于 v{refresh_version}，当前映射已升到 v{current_version}，"
                "旧结果按新版本优先策略丢弃"
            )
            entry["最近失效原因"] = reason
            self._capture_invalidation(entry, reason)
            return entry, "旧刷新与新版本冲突：已按新版本优先丢弃旧结果，失效记录已落入缓存监控待处理区"
        # 正常写回：同一缓存键只产生这一个可见刷新结果，可见结果完整属于该版本。
        entry["可见版本"] = refresh_version
        entry["pending"] = False
        entry["abnormal"] = False
        return entry, f"缓存键 {entry.get('缓存键')} 刷新完成，可见结果已写回 v{refresh_version}"

    def bump_version(self, entry_id: int) -> tuple[dict[str, Any] | None, str]:
        """换版：映射版本前进一步。可见结果仍完整属于旧版本，直到新刷新写回，两版本不混在同一键下。"""
        entry = self.get_entry(entry_id)
        if entry is None:
            return None, f"缓存命中记录 {entry_id} 不存在或已归档"
        entry["映射版本"] = _as_int(entry.get("映射版本")) + 1
        entry["pending"] = True
        return entry, (
            f"缓存键 {entry.get('缓存键')} 已换版到 v{entry['映射版本']}，"
            "进行中的旧刷新完成时将按新版本优先丢弃"
        )

    def invalidate(self, entry_id: int) -> tuple[dict[str, Any] | None, str]:
        """手动失效：按真实条目累计失效量，失效记录同步落入缓存监控待处理区。"""
        entry = self.get_entry(entry_id)
        if entry is None:
            return None, f"缓存命中记录 {entry_id} 不存在或已归档"
        entry["失效次数"] = _as_int(entry.get("失效次数")) + 1
        entry["abnormal"] = True
        entry["pending"] = True
        reason = "手动失效，等待重新回源"
        entry["最近失效原因"] = reason
        self._capture_invalidation(entry, reason)
        return entry, f"缓存键 {entry.get('缓存键')} 已失效，记录已落入缓存监控待处理区"

    # ------------------------------------------------------------------ 看板与概览
    def dashboard(self) -> dict[str, Any]:
        """缓存命中看板与批次看板：各版本占比、失效记录，全部由真实条目计算，只读。"""
        rows = self._merged_rows()
        total_hits = sum(_as_int(row.get("命中次数")) for row in rows)
        total_invalidations = sum(_as_int(row.get("失效次数")) for row in rows)

        versions: dict[int, dict[str, Any]] = {}
        for row in rows:
            version = _as_int(row.get("可见版本"))
            bucket = versions.setdefault(version, {"版本": f"v{version}", "条目数": 0, "命中次数": 0, "占比": 0.0})
            bucket["条目数"] += 1
            bucket["命中次数"] += _as_int(row.get("命中次数"))
        version_share = sorted(versions.values(), key=lambda item: item["版本"])
        for bucket in version_share:
            bucket["占比"] = round(bucket["命中次数"] / total_hits, 4) if total_hits else 0.0

        batches: dict[str, dict[str, Any]] = {}
        for row in rows:
            template = str(row.get("缓存键模板", ""))
            batch = batches.setdefault(
                template,
                {"缓存键模板": template, "条目数": 0, "命中次数": 0, "失效次数": 0, "版本分布": {}},
            )
            batch["条目数"] += 1
            batch["命中次数"] += _as_int(row.get("命中次数"))
            batch["失效次数"] += _as_int(row.get("失效次数"))
            version_label = f"v{_as_int(row.get('可见版本'))}"
            batch["版本分布"][version_label] = batch["版本分布"].get(version_label, 0) + 1
        batch_board = sorted(batches.values(), key=lambda item: item["缓存键模板"])

        invalidations = [
            {
                "记录编号": row.get("记录编号"),
                "缓存键模板": row.get("缓存键模板"),
                "缓存键": row.get("缓存键"),
                "失效次数": _as_int(row.get("失效次数")),
                "最近失效原因": row.get("最近失效原因") or "—",
            }
            for row in rows
            if _as_int(row.get("失效次数")) > 0
        ]
        return {
            "命中总量": total_hits,
            "失效总量": total_invalidations,
            "异常条目": sum(1 for row in rows if row.get("abnormal")),
            "各版本占比": version_share,
            "批次看板": batch_board,
            "失效记录": invalidations,
        }

    def overview_summary(self) -> dict[str, Any]:
        """运营概览读取的真实命中记录汇总，与看板同源。"""
        board = self.dashboard()
        return {
            "命中总量": board["命中总量"],
            "失效总量": board["失效总量"],
            "异常条目": board["异常条目"],
            "各版本占比": board["各版本占比"],
        }

    # ------------------------------------------------------------------ 内部
    def _find_by_key(self, cache_key: str) -> dict[str, Any] | None:
        for row in store.rows(MODULE):
            if str(row.get("缓存键", "")) == cache_key:
                return row
        return None

    def _capture_invalidation(self, entry: dict[str, Any], reason: str) -> None:
        """失效记录落入缓存监控待处理区：pending=True，由采集监控统一承接。"""
        rows = store.rows(MONITOR_MODULE)
        next_id = _next_id(rows)
        rows.append({
            "id": next_id,
            "status": "待校验",
            "pending": True,
            "abnormal": True,
            "指标编号": f"MONI-CACHE-{next_id:04d}",
            "关联端点": entry.get("关联端点") or "—",
            "成功率阈值": f"缓存键 {entry.get('缓存键')} 失效",
            "延迟阈值": "—",
            "错误率告警": reason,
            "检测频率": "实时",
            "通知渠道": "缓存监控待处理区",
            "静默分钟": "—",
        })


cache_hit_service = CacheHitService()
