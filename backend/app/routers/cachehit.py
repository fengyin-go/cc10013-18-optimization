"""缓存命中数据集接口：按缓存键模板归并的命中读取、版本化回源刷新与失效捕获。

读取路径（列表、看板、导出）全部只读，命中量与失效量不随重复点击变化；
只有 /hit、/refresh、/complete、/bump-version、/invalidate 会改变数据集。
"""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException, Query

from app.schemas import ActionResult, EntryPayload, PageResult
from app.services.cachehit import cache_hit_service

router = APIRouter(prefix="/api/cachehit", tags=["缓存命中数据集"])

service = cache_hit_service


@router.get("", response_model=PageResult[dict])
def list_entries(
    keyword: str | None = Query(default=None, description="按记录编号检索"),
    template: str | None = Query(default=None, description="按缓存键模板归并过滤"),
    page: int = 1,
    size: int = 20,
) -> PageResult[dict]:
    """按缓存键归并后的稳定列表：同一缓存键只出现一次，读取不改任何计数。"""
    if size > 200:
        raise HTTPException(status_code=400, detail="每页最多 200 条，请缩小分页范围")
    items, total = service.list_entries(keyword=keyword, template=template, page=page, size=size)
    return PageResult(items=items, total=total, page=page, size=size)


@router.get("/dashboard")
def dashboard() -> dict[str, Any]:
    """缓存命中看板与批次看板：各版本占比、失效记录，与运营概览同源、只读。"""
    return service.dashboard()


@router.get("/export")
def export_entries() -> dict[str, Any]:
    """导出缓存命中数据集：返回归并后的全量真实条目。"""
    items, total = service.list_entries(page=1, size=10000)
    return {"module": "cachehit", "total": total, "items": items}


@router.post("/hit", response_model=ActionResult)
def record_hit(payload: EntryPayload) -> ActionResult:
    """登记一次真实缓存条目命中：命中量只在这里按条目累计，与页面刷新次数无关。"""
    entry, message = service.record_hit(payload.values)
    if entry is None:
        return ActionResult(ok=False, message=message)
    return ActionResult(ok=True, message=message, entry=entry)


@router.get("/{entry_id}", response_model=dict)
def get_entry(entry_id: int) -> dict:
    """读取单条缓存命中记录明细；不存在时给出可读的错误说明。"""
    entry = service.get_entry(entry_id)
    if entry is None:
        raise HTTPException(status_code=404, detail=f"缓存命中记录 {entry_id} 不存在或已归档")
    return entry


@router.post("/{entry_id}/refresh", response_model=ActionResult)
def start_refresh(entry_id: int) -> ActionResult:
    """开始回源刷新：盖当前映射版本戳；同键已有进行中刷新时拒绝，保证只有一个可见结果。"""
    entry, message = service.start_refresh(entry_id)
    if entry is None:
        return ActionResult(ok=False, message=message)
    return ActionResult(ok=True, message=message, entry=entry)


@router.post("/{entry_id}/complete", response_model=ActionResult)
def complete_refresh(entry_id: int) -> ActionResult:
    """完成刷新：版本一致才写回；旧刷新遇到新版本时按新版本优先丢弃并落监控待处理区。"""
    entry, message = service.complete_refresh(entry_id)
    if entry is None:
        return ActionResult(ok=False, message=message)
    return ActionResult(ok=True, message=message, entry=entry)


@router.post("/{entry_id}/bump-version", response_model=ActionResult)
def bump_version(entry_id: int) -> ActionResult:
    """换版：映射版本前进一步，可见结果仍完整属于旧版本，两个版本不混在同一键下。"""
    entry, message = service.bump_version(entry_id)
    if entry is None:
        return ActionResult(ok=False, message=message)
    return ActionResult(ok=True, message=message, entry=entry)


@router.post("/{entry_id}/invalidate", response_model=ActionResult)
def invalidate(entry_id: int) -> ActionResult:
    """手动失效：按真实条目累计失效量，失效记录落入缓存监控待处理区。"""
    entry, message = service.invalidate(entry_id)
    if entry is None:
        return ActionResult(ok=False, message=message)
    return ActionResult(ok=True, message=message, entry=entry)
