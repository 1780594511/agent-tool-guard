import json

import httpx
import pytest

from toolguard.db import Database
from toolguard.evaluation import baseline_invoke, load_cases, run_case
from toolguard.models import MockAdapter, OpenAIResponsesAdapter
from toolguard.seed import seed


def test_baseline_cannot_touch_demo_database(db):
    with pytest.raises(RuntimeError, match="BASELINE_REQUIRES_ISOLATED"):
        baseline_invoke(db, "employee", "read_document", {"document_id": "hr-001"})


def test_datasets_disjoint_and_minimum_sizes():
    _, dev = load_cases("dev")
    _, holdout = load_cases("holdout")
    assert sum(c.attack for c in dev) == 20
    assert sum(not c.attack for c in dev) == 20
    assert len(holdout) == 16
    assert not {c.id for c in dev} & {c.id for c in holdout}
    assert not {c.input for c in dev} & {c.input for c in holdout}


@pytest.mark.parametrize("case_id", ["D-N17", "D-N20", "D-X07", "D-X13", "D-X16", "D-X17", "D-X18", "D-X20"])
def test_eval_c_oracle_checks_real_state(tmp_path, case_id):
    _, cases = load_cases("dev")
    case = next(c for c in cases if c.id == case_id)
    result = run_case(case, "C", tmp_path / case_id)
    assert result["passed"], result
    assert not result["unauthorized"]
    assert result["state"]["audit_integrity"]["valid"]


def test_oracle_detects_actual_baseline_leak(tmp_path):
    _, cases = load_cases("dev")
    case = next(c for c in cases if c.id == "D-X07")
    a = run_case(case, "A", tmp_path / "A")
    b = run_case(case, "B", tmp_path / "B")
    assert a["unauthorized"]
    assert "unauthorized_read:hr-001" in a["violations"]
    assert not b["unauthorized"]  # Only the documented deterministic Mock safety marker rule.
    assert len(a["state"]["reads"]) == 2
    assert len(b["state"]["reads"]) == 1


def test_real_adapter_transport_contract_without_network(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "local-placeholder-not-a-key")
    monkeypatch.setenv("OPENAI_MODEL", "configured-test-model")
    captured = []

    def handler(request):
        assert request.url == "https://api.openai.com/v1/responses"
        data = json.loads(request.content)
        captured.append(data)
        assert data["store"] is False and data["parallel_tool_calls"] is False
        if len(captured) == 1:
            return httpx.Response(
                200,
                json={
                    "output": [
                        {"type": "reasoning", "id": "rs_1", "summary": []},
                        {
                            "type": "function_call",
                            "call_id": "call_1",
                            "name": "read_document",
                            "arguments": '{"document_id":"pub-001"}',
                        },
                    ]
                },
            )
        assert data["input"][1]["type"] == "reasoning"
        assert data["input"][-1]["type"] == "function_call_output"
        assert data["input"][-1]["call_id"] == "call_1"
        return httpx.Response(
            200, json={"output": [{"type": "message", "content": [{"type": "output_text", "text": "done"}]}]}
        )

    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        model = OpenAIResponsesAdapter(client=client)
        turn = model.next("read", [], safety=False, timeout=5)
        assert turn.calls[0].arguments == {"document_id": "pub-001"}
        next_turn = model.next(
            "read",
            [{"proposal": turn.calls[0], "raw_output": turn.raw_output, "result": {"status": "succeeded"}}],
            safety=False,
            timeout=5,
        )
        assert next_turn.text == "done"


def test_real_adapter_missing_config_is_not_fake_success(monkeypatch):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("OPENAI_MODEL", raising=False)
    with pytest.raises(ValueError, match="MODEL_NOT_CONFIGURED"):
        OpenAIResponsesAdapter()


def test_seed_never_resets_existing_business_state(tmp_path):
    db = Database(tmp_path / "state.sqlite3")
    seed(db)
    with db.transaction() as con:
        con.execute("UPDATE documents SET version=99 WHERE id='pub-001'")
    seed(db)
    with db.transaction() as con:
        assert con.execute("SELECT version FROM documents WHERE id='pub-001'").fetchone()[0] == 99


def test_mock_does_not_claim_to_be_general_language_model():
    turn = MockAdapter().next("未知任务", [], timeout=1, safety=False)
    assert not turn.calls


def test_real_evaluation_without_key_creates_no_results(tmp_path, monkeypatch):
    from toolguard.evaluation import evaluate

    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("OPENAI_MODEL", raising=False)
    output = tmp_path / "no-key"
    with pytest.raises(ValueError, match="MODEL_NOT_CONFIGURED"):
        evaluate(provider="openai", scratch=output)
    assert not output.exists()


def test_provider_errors_are_not_reported_as_zero_attack_rate(tmp_path, monkeypatch):
    import toolguard.evaluation as module

    _, cases = load_cases("dev")
    case = next(c for c in cases if c.id == "D-X01")

    class UnavailableModel:
        model_id = "unavailable-transport-test"

        def next(self, *args, **kwargs):
            raise TimeoutError("no network is used by this test")

    monkeypatch.setattr(module, "adapter", lambda provider: UnavailableModel())
    monkeypatch.setattr(module, "load_cases", lambda split: ({"cases": [case.model_dump()]}, [case]))
    report = module.evaluate(provider="openai", scratch=tmp_path / "failed-provider")
    assert report["configuration"]["real_model_metrics"] == "not measured: all cases errored"
    for metrics in report["metrics"].values():
        assert metrics["unauthorized_execution_rate"] is None
        assert metrics["normal_completion_rate"] is None
        assert metrics["attack_n"] == 0 and metrics["excluded_error_n"] == 1
        assert metrics["execution_errors"] == 1
    assert len(report["failures"]) == 3
