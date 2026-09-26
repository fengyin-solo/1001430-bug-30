"""照明设施业务规则：状态流转、字段校验与筛选口径都收在这里。"""
from __future__ import annotations

from datetime import date
from typing import Any

from app.store import store

MODULE = "light"
REQUIRED_FIELDS = ["设施编号", "灯杆编号", "灯具类型"]
STATUS_ORDER = ["待检修", "检修中", "正常亮灯", "缺亮待修", "已停用"]
ACTIONS = ["安排检修", "确认正常", "确认异常", "停用设施"]
# 安排检修只允许从待检修、正常亮灯、缺亮待修发起；检修中、已停用一律拦下。
SCHEDULE_ALLOWED = ["待检修", "正常亮灯", "缺亮待修"]
CONCLUDE_ALLOWED = ["检修中"]
MAINTENANCE_FIELDS = ["检修人", "检修结论", "不合规项"]


def _today() -> str:
    return date.today().isoformat()


def _lamp_rate(value: Any) -> float | None:
    """把亮灯率解析成百分数；停用或写不进数字的记录不参与平均。"""
    if value is None:
        return None
    text = str(value).strip().rstrip("%").strip()
    if not text:
        return None
    try:
        return float(text)
    except ValueError:
        return None


class LightService:
    def list_entries(
        self,
        *,
        keyword: str | None = None,
        status: str | None = None,
        page: int = 1,
        size: int = 20,
    ) -> tuple[list[dict[str, Any]], int]:
        rows = store.rows(MODULE)
        if keyword:
            rows = [row for row in rows if keyword in str(row.get("设施编号", ""))]
        if status:
            rows = [row for row in rows if row.get("status") == status]
        total = len(rows)
        start = max(page - 1, 0) * size
        return rows[start:start + size], total

    def get_entry(self, entry_id: int) -> dict[str, Any] | None:
        return store.find(MODULE, entry_id)

    def create_entry(self, values: dict[str, Any]) -> tuple[dict[str, Any] | None, list[str]]:
        missing = [field for field in REQUIRED_FIELDS if not str(values.get(field) or "").strip()]
        if missing:
            return None, missing
        rows = store.rows(MODULE)
        entry = {"id": max((int(row.get("id", 0)) for row in rows), default=0) + 1}
        entry.update({field: values.get(field) for field in REQUIRED_FIELDS})
        entry["status"] = STATUS_ORDER[0]
        entry["设施状态"] = STATUS_ORDER[0]
        entry["pending"] = True
        entry["abnormal"] = False
        for field in MAINTENANCE_FIELDS:
            entry[field] = ""
        entry["检修记录"] = []
        rows.append(entry)
        return entry, []

    def stats(self) -> dict[str, Any]:
        """列表页统计口径：在册件数、缺亮待修件数、平均亮灯率（不含已停用）。"""
        rows = store.rows(MODULE)
        active = [row for row in rows if row.get("status") != "已停用"]
        rates = [rate for rate in (_lamp_rate(row.get("亮灯率")) for row in active) if rate is not None]
        return {
            "在册照明设施": len(active),
            "缺亮待修": sum(1 for row in rows if row.get("status") == "缺亮待修"),
            "平均亮灯率": f"{sum(rates) / len(rates):.1f}%" if rates else "—",
        }

    def run_action(
        self,
        entry_id: int,
        action: str,
        values: dict[str, Any] | None = None,
    ) -> tuple[dict[str, Any] | None, str]:
        entry = store.find(MODULE, entry_id)
        if entry is None:
            return None, f"照明设施 {entry_id} 不存在或已归档"
        if action not in ACTIONS:
            return None, f"动作「{action}」不属于照明设施可执行范围"
        values = values or {}
        if action == "安排检修":
            return self._schedule(entry, values)
        if action == "确认正常":
            return self._conclude(entry, "正常亮灯", "")
        if action == "确认异常":
            return self._conclude(entry, "缺亮待修", str(values.get("不合规项") or "").strip())
        return self._disable(entry)

    def _schedule(self, entry: dict[str, Any], values: dict[str, Any]) -> tuple[dict[str, Any] | None, str]:
        status = str(entry.get("status") or "")
        if status not in SCHEDULE_ALLOWED:
            return None, f"照明设施当前为「{status}」，已停用或检修中的设施不允许再安排检修"
        operator = str(values.get("检修人") or "").strip()
        if not operator:
            return None, "安排检修需要填写检修人"
        entry["status"] = "检修中"
        entry["设施状态"] = "检修中"
        entry["pending"] = True
        entry["abnormal"] = False
        entry["检修人"] = operator
        entry["检修结论"] = ""
        entry["不合规项"] = ""
        entry.setdefault("检修记录", []).append(
            {"动作": "安排检修", "检修人": operator, "时间": _today(), "结果": "进入检修中"}
        )
        return entry, f"照明设施已安排检修，检修人：{operator}"

    def _conclude(
        self,
        entry: dict[str, Any],
        target: str,
        defect: str,
    ) -> tuple[dict[str, Any] | None, str]:
        status = str(entry.get("status") or "")
        if status not in CONCLUDE_ALLOWED:
            return None, f"照明设施当前为「{status}」，只有检修中的设施才能确认检修结论"
        if target == "缺亮待修" and not defect:
            return None, "确认异常需要写清不合规项"
        entry["status"] = target
        entry["设施状态"] = target
        entry["pending"] = target == "缺亮待修"
        entry["abnormal"] = target == "缺亮待修"
        entry["不合规项"] = defect
        entry["检修结论"] = "确认异常" if target == "缺亮待修" else "确认正常"
        entry["上次检修日"] = _today()
        entry.setdefault("检修记录", []).append(
            {
                "动作": entry["检修结论"],
                "检修人": str(entry.get("检修人") or ""),
                "时间": _today(),
                "结果": defect if target == "缺亮待修" else "恢复亮灯",
            }
        )
        if target == "缺亮待修":
            return entry, f"照明设施检修结论为异常，转入缺亮待修：{defect}"
        return entry, "照明设施检修结论为正常，已恢复正常亮灯"

    def _disable(self, entry: dict[str, Any]) -> tuple[dict[str, Any] | None, str]:
        if entry.get("status") == "已停用":
            return None, "照明设施已停用，无需重复停用"
        entry["status"] = "已停用"
        entry["设施状态"] = "已停用"
        entry["pending"] = False
        entry["abnormal"] = False
        return entry, "照明设施已停用"
