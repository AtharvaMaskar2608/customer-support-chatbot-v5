"""Round-trip tests for the shared data contracts and SSE event union."""

import pytest
from pydantic import TypeAdapter, ValidationError

from backend.contracts.events import (
    CardOption,
    CardStep,
    CitationsEvent,
    DateRangeStep,
    DoneEvent,
    ErrorEvent,
    ReportRequestEvent,
    SSEEvent,
    StatusEvent,
    TokenEvent,
    UsageEvent,
    WidgetStep,
)
from backend.contracts.models import (
    AgentReply,
    Citation,
    RagChunk,
    RagResult,
    ReportColumn,
    ReportRenderPayload,
    ReportResult,
    Session,
    Usage,
)

_widget_step = TypeAdapter(WidgetStep)

_sse = TypeAdapter(SSEEvent)


def test_rag_result_round_trip():
    citation = Citation(
        topic="Onboarding",
        section="KYC",
        question="How do I complete KYC?",
        answer_source="faq.xlsx",
        source_sheet="Sheet1",
        source_row=42,
    )
    result = RagResult(
        query="kyc help",
        chunks=(RagChunk(id=1, chunk="Complete KYC via the app.", score=0.91, citation=citation),),
    )
    assert RagResult.model_validate(result.model_dump()) == result


def test_report_result_failure_shape():
    failed = ReportResult(ok=False, data=None, error="upstream 500")
    assert failed.ok is False and failed.data is None
    assert ReportResult.model_validate(failed.model_dump()) == failed


def test_session_and_agent_reply_round_trip():
    session = Session(
        client_code="X130627", user_id="u1", mobile_no="9920885615", session_token="jwt.abc.def"
    )
    assert Session.model_validate(session.model_dump()) == session

    reply = AgentReply(
        text="Here is your answer.",
        citations=(Citation(topic="Reports"),),
        usage=Usage(input_tokens=10, output_tokens=20, cost_inr=0.5, latency_ms=120.0, cumulative_cost_inr=1.5),
    )
    assert AgentReply.model_validate(reply.model_dump()) == reply


def test_session_finx_session_id_default_and_explicit():
    default = Session(
        client_code="X130627", user_id="u1", mobile_no="9920885615", session_token="jwt"
    )
    assert default.finx_session_id == ""

    explicit = Session(
        client_code="X130627",
        user_id="u1",
        mobile_no="9920885615",
        session_token="jwt",
        finx_session_id="abc123",
    )
    assert explicit.finx_session_id == "abc123"
    assert Session.model_validate(explicit.model_dump()) == explicit


def test_agent_reply_tools_called_default_and_explicit():
    assert AgentReply(text="hi").tools_called == ()

    reply = AgentReply(text="pulling your ledger", tools_called=("ledger",))
    assert reply.tools_called == ("ledger",)
    assert AgentReply.model_validate(reply.model_dump()) == reply


def test_report_render_payload_table_shape():
    payload = ReportRenderPayload(
        kind="table",
        title="MTF Ledger · 2026-04-01 → 2026-07-15",
        columns=(ReportColumn(key="Narration", label="Description"),),
        rows=({"Narration": "Opening balance"},),
    )
    dumped = payload.model_dump()
    assert dumped["kind"] == "table"
    assert dumped["columns"] == ({"key": "Narration", "label": "Description"},)
    assert dumped["rows"] == ({"Narration": "Opening balance"},)
    assert ReportRenderPayload.model_validate(dumped) == payload


def test_report_render_payload_link_empty_error_shapes():
    link = ReportRenderPayload(kind="link", title="Tax Report", url="https://x/report.pdf")
    assert link.url == "https://x/report.pdf" and link.columns == () and link.rows == ()

    empty = ReportRenderPayload(kind="empty", title="Ledger", message="Data not found.")
    assert empty.message == "Data not found." and empty.url is None

    error = ReportRenderPayload(kind="error", title="Ledger", message="upstream 500")
    for payload in (link, empty, error):
        assert ReportRenderPayload.model_validate(payload.model_dump()) == payload


def test_models_are_frozen():
    citation = Citation(topic="x")
    with pytest.raises(ValidationError):
        citation.topic = "y"  # type: ignore[misc]


@pytest.mark.parametrize(
    "event",
    [
        StatusEvent(message="searching"),
        TokenEvent(text="hello"),
        CitationsEvent(citations=[Citation(topic="t")]),
        UsageEvent(usage=Usage(cumulative_cost_inr=2.0)),
        ReportRequestEvent(report_type="contract_notes", tool_use_id="tu_1"),
        ReportRequestEvent(
            report_type="ledger",
            steps=[
                CardStep(
                    param="group",
                    options=(
                        CardOption(label="Normal Ledger", value="Group1"),
                        CardOption(label="MTF Ledger", value="MTF"),
                    ),
                ),
                DateRangeStep(from_param="from_date", to_param="to_date"),
            ],
            tool_use_id="tu_2",
        ),
        DoneEvent(stop_reason="end_turn"),
        ErrorEvent(message="boom"),
    ],
)
def test_sse_event_discriminated_round_trip(event):
    dumped = event.model_dump()
    assert _sse.validate_python(dumped) == event


def test_usage_frame_carries_cumulative_cost():
    dumped = UsageEvent(usage=Usage(cumulative_cost_inr=3.14)).model_dump()
    assert dumped["type"] == "usage"
    assert dumped["usage"]["cumulative_cost_inr"] == 3.14


def test_report_request_steps_default_empty():
    """``steps`` defaults to ``[]`` and the legacy ``fields`` attribute is gone."""
    modern = ReportRequestEvent(report_type="tax_report", tool_use_id="tu_2")
    assert modern.steps == []
    assert not hasattr(modern, "fields")


def test_widget_step_deserializes_by_kind():
    cards = _widget_step.validate_python(
        {"kind": "cards", "param": "group", "options": [{"label": "MTF", "value": "MTF"}]}
    )
    assert isinstance(cards, CardStep) and cards.options[0].value == "MTF"

    date_range = _widget_step.validate_python({"kind": "date_range"})
    assert isinstance(date_range, DateRangeStep)
    assert date_range.from_param == "from_date" and date_range.to_param == "to_date"


def test_widget_step_unknown_kind_rejected():
    with pytest.raises(ValidationError):
        _widget_step.validate_python({"kind": "dropdown", "param": "group"})
