import json
from pathlib import Path

from app.schemas.export_json_schema import DEFAULT_OUT, build


def test_export_contains_the_public_models():
    schema = build()
    defs = schema["$defs"]
    for name in ("SessionOut", "ConversationSummary", "ConversationDetail", "GuestThread",
                 "MessageOut", "WorkOrderOut", "WorkOrderDetail", "WorkOrderPrefill",
                 "QuickReplyOut", "AssetOut", "CategoryOut",
                 "NotificationOut", "Overview", "AgentStats", "StaffUserOut", "DepartmentOut",
                 "SimGuest", "StaffConversationOut", "StaffMessageOut",
                 "LogEntryOut", "LogFeedOut", "LogMentionableOut",
                 "UnitOut", "UnitImportOut", "TemplateOut", "SweepOut", "RunOut",
                 "InspectionRowOut", "CycleOut", "ComplianceOut"):
        assert name in defs, name
    assert defs["GuestThread"]["additionalProperties"] is False
    assert "notes" not in defs["GuestThread"]["properties"]


def test_committed_schema_is_current():
    path = Path(DEFAULT_OUT)
    assert path.exists(), f"run: python -m app.schemas.export_json_schema  (writes {path})"
    committed = json.loads(path.read_text(encoding="utf-8"))
    assert committed == build(), ("web/src/api/schema.json is stale — "
                                  "re-run python -m app.schemas.export_json_schema")
