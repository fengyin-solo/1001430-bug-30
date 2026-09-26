"""照明设施接口：维护照明设施，覆盖安排检修、确认正常、确认异常、停用设施等动作。"""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException, Query

from app.schemas import ActionResult, EntryPayload, PageResult
from app.services.light import LightService

router = APIRouter(prefix="/api/light", tags=["照明设施"])

service = LightService()

LIST_FIELDS = ["设施编号", "灯杆编号", "灯具类型", "所在道路", "亮灯率", "上次检修日", "责任班组", "设施状态"]
STATUSES = ["待检修", "检修中", "正常亮灯", "缺亮待修", "已停用"]


@router.get("", response_model=PageResult[dict])
def list_entries(
    keyword: str | None = Query(default=None, description="按设施编号检索"),
    status: str | None = Query(default=None, description="待检修、正常亮灯、缺亮待修、已停用"),
    page: int = 1,
    size: int = 20,
) -> PageResult[dict]:
    """按设施编号与状态过滤照明设施列表；没有数据时返回空页，不报错。"""
    if size > 200:
        raise HTTPException(status_code=400, detail="每页最多 200 条，请缩小分页范围")
    items, total = service.list_entries(keyword=keyword, status=status, page=page, size=size)
    return PageResult(items=items, total=total, page=page, size=size)


@router.get("/summary")
def summary() -> dict[str, Any]:
    """汇总照明设施：在册数量、缺亮待修件数与平均亮灯率，口径与列表明细一致。"""
    return service.summary()


@router.get("/{entry_id}", response_model=dict)
def get_entry(entry_id: int) -> dict:
    """读取单条照明设施明细；不存在时给出可读的错误说明。"""
    entry = service.get_entry(entry_id)
    if entry is None:
        raise HTTPException(status_code=404, detail=f"照明设施 {entry_id} 不存在或已归档")
    return entry


@router.post("", response_model=ActionResult)
def create_entry(payload: EntryPayload) -> ActionResult:
    """登记一条照明设施，缺字段时说明原因而不是静默丢弃。"""
    entry, missing = service.create_entry(payload.values)
    if missing:
        return ActionResult(ok=False, message=f"缺少必填字段：{'、'.join(missing)}")
    return ActionResult(ok=True, message="照明设施已登记", entry=entry)


@router.post("/{entry_id}/actions", response_model=ActionResult)
def run_action(entry_id: int, payload: EntryPayload) -> ActionResult:
    """对单条照明设施执行安排检修、确认正常、确认异常、停用设施；不允许的动作会被拦下并说明原因。"""
    entry, message = service.run_action(entry_id, payload.values)
    if entry is None:
        return ActionResult(ok=False, message=message)
    return ActionResult(ok=True, message=message, entry=entry)


@router.get("/export")
def export_entries() -> dict[str, Any]:
    """导出照明设施清单：返回当前过滤条件下的全量数据。"""
    items, total = service.list_entries(page=1, size=10000)
    return {"module": "light", "total": total, "items": items}
