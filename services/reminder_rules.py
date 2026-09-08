from datetime import datetime
from typing import Any


def build_operational_reminder(signal: dict[str, Any], now: datetime) -> dict[str, Any]:
    """Convert one trusted operational signal into an internal reminder draft."""
    signal_type = signal["signal_type"]
    source_id = signal["source_id"]

    if signal_type == "task_due":
        due_at = signal["due_at"]
        overdue = due_at < now
        return {
            "task_id": source_id,
            "member_id": signal.get("member_id"),
            "reminder_type": "task_due",
            "source_type": "task",
            "source_id": source_id,
            "dedup_key": f"task_due:{source_id}:{due_at.isoformat()}",
            "title": f"{'逾期' if overdue else '即將到期'}：{signal['title']}",
            "scheduled_at": now,
            "payload": {
                "severity": "urgent" if overdue else "high",
                "reason": "任務已超過期限" if overdue else "任務將在 24 小時內到期",
                "recommended_action": "確認負責人與最新處理進度",
                "due_at": due_at.isoformat(),
            },
        }

    if signal_type == "payment_follow_up":
        return {
            "task_id": None,
            "member_id": signal.get("member_id"),
            "reminder_type": "payment_follow_up",
            "source_type": "order",
            "source_id": source_id,
            "dedup_key": f"payment_follow_up:{source_id}:{signal['created_at'].date().isoformat()}",
            "title": f"待付款訂單：{signal['order_number']}",
            "scheduled_at": now,
            "payload": {
                "severity": "high",
                "reason": "訂單建立超過 24 小時仍未完成付款",
                "recommended_action": "由顧問確認付款狀態，再決定是否聯絡旅客",
                "order_number": signal["order_number"],
                "amount": str(signal["total"]),
                "currency": signal["currency"],
            },
        }

    if signal_type == "trip_countdown":
        return {
            "task_id": None,
            "member_id": signal.get("member_id"),
            "reminder_type": "trip_countdown",
            "source_type": "travel_request",
            "source_id": source_id,
            "dedup_key": f"trip_countdown:{source_id}:{signal['start_date'].isoformat()}",
            "title": f"出發前確認：{signal['title']}",
            "scheduled_at": now,
            "payload": {
                "severity": "normal",
                "reason": "旅程將在 14 天內出發",
                "recommended_action": "確認文件、付款、聯絡資訊與最後行程版本",
                "destination": signal["destination"],
                "start_date": signal["start_date"].isoformat(),
            },
        }

    if signal_type == "agent_proposal_sla":
        remaining_minutes = max(
            0, int((signal["expires_at"] - now).total_seconds() // 60)
        )
        return {
            "task_id": None,
            "member_id": None,
            "reminder_type": "agent_proposal_sla",
            "source_type": "agent_action_proposal",
            "source_id": source_id,
            "dedup_key": f"agent_proposal_sla:{source_id}:{signal['expires_at'].isoformat()}",
            "title": f"Agent 提案即將到期：{signal['title']}",
            "scheduled_at": now,
            "payload": {
                "severity": "urgent" if remaining_minutes <= 60 else "high",
                "reason": f"待核准提案將在 {remaining_minutes} 分鐘內到期",
                "recommended_action": "確認負責人並完成核准或退回",
                "proposal_id": source_id,
                "assigned_to": signal.get("assigned_to"),
                "expires_at": signal["expires_at"].isoformat(),
            },
        }

    raise ValueError(f"Unsupported reminder signal: {signal_type}")
