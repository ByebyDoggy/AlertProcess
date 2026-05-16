from detection import DetectionContext, DetectionEvidence, DetectionResult, score_to_severity


def test_detection_context_from_dict_preserves_standard_and_enrichment_fields():
    ctx = DetectionContext.from_dict({
        "chain_id": 56,
        "tx_hash": "0xabc",
        "block_number": 123,
        "timestamp": "2026-05-16T00:00:00Z",
        "from_address": "0xAaAa",
        "to_address": "0xBbBb",
        "value": "0x10",
        "input_data": "0x12345678",
        "logs": [{"address": "0xToken"}],
        "trace_calls": [{"caller": "0x1", "callee": "0x2"}],
        "transfers": [{"token": "0xToken", "from": "0x1", "to": "0x2", "amount_raw": "100"}],
        "balance_changes": [{"address": "0x1", "token": "0xToken", "delta": "-100"}],
        "token_prices": {"0xToken": 1.5},
        "address_labels": {"0x2": "LP Pair"},
        "custom_field": "kept",
    })

    assert ctx.chain_id == 56
    assert ctx.tx_hash == "0xabc"
    assert ctx.from_address == "0xaaaa"
    assert ctx.to_address == "0xbbbb"
    assert ctx.value == 16
    assert ctx.trace_calls == [{"caller": "0x1", "callee": "0x2"}]
    assert ctx.transfers[0]["amount_raw"] == "100"
    assert ctx.metadata["custom_field"] == "kept"


def test_detection_context_reports_missing_required_inputs():
    ctx = DetectionContext.from_dict({"chain_id": 56, "tx_hash": "0xabc", "transfers": []})

    assert ctx.missing_inputs(["transfers", "trace_calls", "token_prices"]) == ["trace_calls", "token_prices"]


def test_detection_result_sets_passed_from_threshold_and_severity_from_score():
    result = DetectionResult.from_score(
        script_id="sample_script",
        score=91.0,
        threshold=40.0,
        attack_type="sample_attack",
        labels=["sample"],
        evidence=[DetectionEvidence(kind="FLOW", description="fund flow", weight=50.0, data={"x": 1})],
    )

    assert result.passed is True
    assert result.severity == "CRITICAL"
    assert result.script_id == "sample_script"
    assert result.evidence[0].kind == "FLOW"
    assert result.summary == "sample_attack detected by sample_script"


def test_score_to_severity_boundaries():
    assert score_to_severity(0) == "UNKNOWN"
    assert score_to_severity(10) == "LOW"
    assert score_to_severity(45) == "MEDIUM"
    assert score_to_severity(70) == "HIGH"
    assert score_to_severity(90) == "CRITICAL"
