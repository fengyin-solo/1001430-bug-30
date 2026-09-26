"""照明设施业务规则：状态流转、字段校验与筛选口径都收在这里。"""
from __future__ import annotations

from datetime import date
from typing import Any

from app.store import store

MODULE = "light"
REQUIRED_FIELDS = ["设施编号", "灯杆编号", "灯具类型"]
STATUS_ORDER = ["待检修", "检修中", "正常亮灯", "缺亮待修", "已停用"]

# 动作 -> (允许的前置状态, 目标状态)；已停用与检修中不允许再安排检修
ACTION_RULES = {
    "安排检修": (["待检修", "正常亮灯", "缺亮待修"], "检修中"),
    "确认正常": (["检修中"], "正常亮灯"),
    "确认异常": (["检修中"], "缺亮待修"),
    "停用设施": (["待检修", "检修中", "正常亮灯", "缺亮待修"], "已停用"),
}

# 状态 -> (是否待处理, 是否异常)，供运营概览汇总
STATUS_FLAGS = {
    "待检修": (True, False),
    "检修中": (True, False),
    "正常亮灯": (False, False),
    "缺亮待修": (True, True),
    "已停用": (False, False),
}


def _apply_status(entry: dict[str, Any], status: str) -> None:
    entry["status"] = status
    entry["设施状态"] = status
    entry["pending"], entry["abnormal"] = STATUS_FLAGS[status]


def _parse_rate(value: Any) -> float | None:
    if isinstance(value, (int, float)):
        return float(value)
    text = str(value or "").strip().rstrip("%")
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
        _apply_status(entry, STATUS_ORDER[0])
        entry["检修人"] = ""
        entry["不合规项"] = ""
        entry["检修记录"] = []
        rows.append(entry)
        return entry, []

    def run_action(self, entry_id: int, values: dict[str, Any]) -> tuple[dict[str, Any] | None, str]:
        entry = store.find(MODULE, entry_id)
        if entry is None:
            return None, f"照明设施 {entry_id} 不存在或已归档"
        action = str(values.get("action") or "").strip()
        if action not in ACTION_RULES:
            return None, f"动作「{action}」不属于照明设施可执行范围"
        allowed_from, target = ACTION_RULES[action]
        current = str(entry.get("status") or "")
        if current not in allowed_from:
            return None, f"照明设施当前为「{current}」，不允许{action}"
        if action == "安排检修":
            operator = str(values.get("检修人") or "").strip() or str(entry.get("责任班组") or "").strip()
            if not operator:
                return None, "安排检修需先记下检修人"
            entry["检修人"] = operator
        if action == "确认异常":
            defect = str(values.get("不合规项") or "").strip()
            if not defect:
                return None, "确认异常需写清是哪一头不合规"
            entry["不合规项"] = defect
        if action == "确认正常":
            entry["不合规项"] = ""
        if action in ("确认正常", "确认异常"):
            entry["上次检修日"] = date.today().isoformat()
        _apply_status(entry, target)
        record = {
            "日期": date.today().isoformat(),
            "动作": action,
            "检修人": entry.get("检修人") or "—",
            "结果状态": target,
        }
        if action == "确认异常":
            record["不合规项"] = entry["不合规项"]
        entry.setdefault("检修记录", []).append(record)
        if action == "确认异常":
            return entry, f"照明设施已确认异常，不合规项：{entry['不合规项']}"
        if action == "停用设施":
            return entry, "照明设施已停用"
        return entry, f"照明设施已{action}"

    def summary(self) -> dict[str, Any]:
        """列表页统计口径：在册数量、缺亮待修件数、在营设施的平均亮灯率。"""
        rows = store.rows(MODULE)
        active = [row for row in rows if row.get("status") != "已停用"]
        rates = [rate for row in active if (rate := _parse_rate(row.get("亮灯率"))) is not None]
        average = round(sum(rates) / len(rates), 1) if rates else 0.0
        return {
            "在册照明设施": len(rows),
            "缺亮待修": sum(1 for row in rows if row.get("status") == "缺亮待修"),
            "平均亮灯率": average,
        }
