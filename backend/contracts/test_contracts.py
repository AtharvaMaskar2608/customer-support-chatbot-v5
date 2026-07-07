"""Round-trip tests for the shared data contracts and SSE event union."""

import pytest
from pydantic import TypeAdapter, ValidationError

from backend.contracts.events import (
    CitationsEvent,
    DoneEvent,
    ErrorEvent,
    ReportRequestEvent,
    SSEEvent,
    StatusEvent,
    TokenEvent,
    UsageEvent,
)
from backend.contracts.models import (
    AgentReply,
    Citation,
    RagChunk,
    RagResult,
    ReportResult,
    Session,
    Usage,
)

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
        ReportRequestEvent(report_type="cml", fields=["client_id"], tool_use_id="tu_1"),
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
