"""Tests for the evaluation helpers."""
from app.services.evaluation_service import (
    evaluate_approval_routing,
    evaluate_data_pipeline,
    evaluate_retrieval,
    evaluate_risk_scoring,
    run_evaluation,
)


def test_risk_scoring_separation(session):
    res = evaluate_risk_scoring(session)
    assert res["passed"]
    assert res["risky_score"] >= 0.6
    assert res["clean_score"] < 0.6


def test_approval_routing_checks(session):
    res = evaluate_approval_routing(session)
    assert res["passed"]
    assert res["high_risk_change_route"] == "pending"
    assert res["approved_route"] == "writeback"
    assert res["rejected_route"] == "finalize"


def test_retrieval_scoped_accuracy(session):
    res = evaluate_retrieval(session)
    assert res["passed"]
    assert res["samples"] >= 1


def test_data_pipeline_integrity(session):
    res = evaluate_data_pipeline(session)
    assert res["passed"]
    assert res["counts"]["vector_documents"] > 0


def test_full_evaluation_all_pass_on_demo_data(session):
    result = run_evaluation(session)
    assert result["summary"]["all_passed"], result
