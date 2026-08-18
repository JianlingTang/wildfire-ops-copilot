from app.models.schemas import Aoi, ChatRequest
from app.services.request_scope import is_wildfire_operations_request, out_of_scope_response


def test_scope_gate_accepts_explicit_wildfire_requests_in_english_and_chinese() -> None:
    assert is_wildfire_operations_request(ChatRequest(message="Explain this wildfire hotspot."))
    assert is_wildfire_operations_request(ChatRequest(message="分析这个区域的山火风险"))


def test_scope_gate_accepts_contextual_operational_requests() -> None:
    assert is_wildfire_operations_request(
        ChatRequest(message="How did wind change since yesterday?", run_id="run_123")
    )
    assert is_wildfire_operations_request(
        ChatRequest(message="Calculate the risk percent change.", aoi=Aoi(center=(-12.4, 132.9), radius_km=50))
    )
    assert is_wildfire_operations_request(
        ChatRequest(message="What about tomorrow?", conversation_id="conv_123")
    )


def test_scope_gate_blocks_unrelated_requests_even_with_a_run() -> None:
    assert not is_wildfire_operations_request(ChatRequest(message="What is 2 + 2?"))
    assert not is_wildfire_operations_request(ChatRequest(message="Write a wedding poem.", run_id="run_123"))
    assert not is_wildfire_operations_request(ChatRequest(message="How do I configure a firewall?"))
    assert not is_wildfire_operations_request(
        ChatRequest(message="What about football?", conversation_id="conv_123")
    )


def test_out_of_scope_response_records_that_no_llm_was_called() -> None:
    response = out_of_scope_response(mode="adk")

    assert response["intent"] == "OUT_OF_SCOPE"
    assert response["response"]["status"] == "blocked"
    assert response["response"]["llm_called"] is False
    assert response["response"]["tool_trace"][0]["called"] == "Domain Scope Gate"
