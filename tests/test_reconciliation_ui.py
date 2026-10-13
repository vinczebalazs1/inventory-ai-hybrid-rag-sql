"""UI behavior with real Streamlit reruns and no external service calls."""
from types import SimpleNamespace
from unittest.mock import Mock

import pytest
from streamlit.testing.v1 import AppTest

from app.document_processing.models import (
    ExtractionResult, MappedField, MappingResult, ParsedDocument, ProcessingResult,
)
from app.errors import AppError
from app.record_matching.models import (
    ActionType, CandidateRecord, ComparisonStatus, FieldComparison, MatchStatus,
    ProcessingMetadata, ReconciliationResult, ScoreContribution, SearchMetadata,
    SuggestedAction,
)
from app.web import document_preview, reconciliation_preview


def analysis():
    return ProcessingResult(
        parsed_document=ParsedDocument(
            source_name="asset.pdf", source_extension=".pdf",
            markdown="Location: Budapest", extraction_text="Location: Budapest",
        ),
        extraction=ExtractionResult(source_name="asset.pdf", fields=[]),
        mapping=MappingResult(mapped_fields=[MappedField(
            source_label="Location", raw_value="Budapest", target_field="location",
            normalized_value="Budapest", evidence="Location: Budapest", page=1,
        )]),
        validation_issues=[],
    )


def reconciliation(status=MatchStatus.EXACT_MATCH):
    candidate = CandidateRecord(
        record_id='inventory_items:{"item_code":"A001"}', identity_fields=["item_code"],
        values={"item_code": "A001", "name": "Dell Laptop", "location": "Győr"},
        rank=1, similarity_score=1.0, strategy="exact_identifier",
        matching_fields=["item_code"],
        score_breakdown=[ScoreContribution(
            field="item_code", similarity=1.0, weight=5.0, contribution=5.0,
            explanation="Pontos azonosítóegyezés.",
        )],
        reasons=["Az item_code egyedi kulcs alapján egyezik."],
        verified_identifier_match=True,
    )
    return ReconciliationResult(
        source_document="asset.pdf", match_status=status,
        matched_record=candidate if status == MatchStatus.EXACT_MATCH else None,
        candidates=[candidate],
        field_comparisons=[FieldComparison(
            field="location", source_label="Location", raw_document_value="Budapest",
            normalized_document_value="Budapest", database_value="Győr",
            status=ComparisonStatus.DIFFERENT, evidence="Location: Budapest", page=1,
            explanation="A helyszín eltér.", record_id=candidate.record_id,
        )],
        suggested_actions=[SuggestedAction(
            action_type=ActionType.UPDATE_CANDIDATE, target_record=candidate.record_id,
            reason="Eltérő helyszín ellenőrzése.", affected_fields=["location"],
            limitations=["A javaslat nem hajtható végre ezen a felületen."],
        )],
        reasons=["Ellenőrizd a dokumentumbeli helyszínt."],
        search_metadata=SearchMetadata(complete=True, scope="small_table", candidate_limit=100),
        processing_metadata=ProcessingMetadata(strategy="hybrid"),
    )


def app_with_analysis(*, debug=False):
    app = AppTest.from_string(
        "from app.web.document_preview import render_document_analysis\n"
        f"render_document_analysis(show_debug={debug!r})\n"
    )
    app.session_state["document_preview"] = analysis()
    return app


def test_reconciliation_requires_click_and_is_cached_across_reruns(monkeypatch):
    run = Mock(return_value=reconciliation())
    llm = Mock(side_effect=AssertionError("UI must reuse the existing analysis"))
    monkeypatch.setattr(reconciliation_preview, "_run_reconciliation", run)
    monkeypatch.setattr(document_preview, "process_document", llm)
    app = app_with_analysis().run()
    assert not app.exception
    run.assert_not_called()
    app.button(key="reconcile_document").click().run()
    assert not app.exception
    run.assert_called_once_with(app.session_state["document_preview"])
    app.run()
    assert not app.exception
    assert run.call_count == 1
    llm.assert_not_called()


def test_ranking_evidence_differences_and_advisory_actions_render(monkeypatch):
    result = reconciliation()
    before = result.model_dump_json()
    monkeypatch.setattr(reconciliation_preview, "_run_reconciliation", lambda _: result)
    app = app_with_analysis().run()
    app.button(key="reconcile_document").click().run()
    assert not app.exception
    tables = [element.value for element in app.dataframe]
    ranking = next(table for table in tables if "Rang" in table.columns)
    assert ranking.iloc[0]["item_code"] == "A001"
    assert ranking.iloc[0]["Hasonlósági pontszám"] == 1.0
    comparison = next(table for table in tables if "Eltérés" in table.columns)
    assert comparison.iloc[0]["Státusz"] == "DIFFERENT"
    assert comparison.iloc[0]["Bizonyíték"] == "Location: Budapest"
    assert comparison.iloc[0]["Adatbázis"] == "Győr"
    assert any("Rekordfrissítés javaslata" in element.value for element in app.markdown)
    assert any("Emberi ellenőrzés" in element.value for element in app.warning)
    assert {button.label for button in app.button} == {"Analyze document", "Egyeztetés az adatbázissal"}
    assert result.model_dump_json() == before


@pytest.mark.parametrize("status", [
    MatchStatus.LIKELY_MATCH, MatchStatus.AMBIGUOUS_MATCH,
    MatchStatus.CONFLICTING_DATA, MatchStatus.INSUFFICIENT_DATA,
    MatchStatus.NO_MATCH, MatchStatus.ERROR, MatchStatus.SEARCH_INCOMPLETE,
])
def test_all_statuses_render_without_hiding_review(monkeypatch, status):
    result = reconciliation(status)
    result.candidates = []
    result.field_comparisons = []
    result.suggested_actions = []
    result.search_metadata.complete = status == MatchStatus.NO_MATCH
    monkeypatch.setattr(reconciliation_preview, "_run_reconciliation", lambda _: result)
    app = app_with_analysis().run()
    app.button(key="reconcile_document").click().run()
    assert not app.exception
    assert any(element.value == status.value for element in app.caption)
    assert any("emberi ellenőrzést" in element.value for element in app.warning)
    if not result.search_metadata.complete:
        assert any("keresés nem teljes" in element.value for element in app.warning)


def test_failure_preserves_analysis_sanitizes_details_and_allows_retry(monkeypatch):
    secret = "postgres://user:password@host/private-document"
    run = Mock(side_effect=[RuntimeError(secret), reconciliation()])
    monkeypatch.setattr(reconciliation_preview, "_run_reconciliation", run)
    app = app_with_analysis(debug=True).run()
    before = app.session_state["document_preview"].model_dump_json()
    app.button(key="reconcile_document").click().run()
    assert not app.exception
    assert app.session_state["document_preview"].model_dump_json() == before
    assert any("dokumentumelemzés megmaradt" in element.value for element in app.error)
    assert secret not in str(app)
    app.run()
    assert run.call_count == 1
    assert app.error
    app.button(key="reconcile_document").click().run()
    assert not app.exception
    assert not app.error
    assert run.call_count == 2


def test_upload_callback_clears_analysis_and_reconciliation(monkeypatch):
    state = {
        "document_preview": analysis(),
        reconciliation_preview.RESULT_KEY: reconciliation(),
        reconciliation_preview.ERROR_KEY: "RuntimeError",
        "unrelated": "keep",
    }
    monkeypatch.setattr(document_preview.st, "session_state", state)
    document_preview._clear_preview()
    assert state == {"unrelated": "keep"}


def test_upload_widget_registers_invalidation_callback(monkeypatch):
    uploader = Mock(return_value=None)
    monkeypatch.setattr(document_preview.st, "file_uploader", uploader)
    app = app_with_analysis().run()
    assert not app.exception
    assert uploader.call_args.kwargs["on_change"] is document_preview._clear_preview


@pytest.mark.parametrize("fails", [False, True])
def test_reanalysis_discards_stale_reconciliation_even_when_analysis_fails(monkeypatch, fails):
    upload = SimpleNamespace(name="asset.pdf", getvalue=lambda: b"pdf")
    monkeypatch.setattr(document_preview.st, "file_uploader", lambda *args, **kwargs: upload)
    process = Mock(side_effect=AppError("Elemzési hiba.")) if fails else Mock(return_value=analysis())
    monkeypatch.setattr(document_preview, "process_document", process)
    run = Mock()
    monkeypatch.setattr(reconciliation_preview, "_run_reconciliation", run)
    app = app_with_analysis()
    app.session_state[reconciliation_preview.RESULT_KEY] = reconciliation()
    app.session_state[reconciliation_preview.ERROR_KEY] = "RuntimeError"
    app.run()
    next(button for button in app.button if button.label == "Analyze document").click().run()
    assert not app.exception
    assert reconciliation_preview.RESULT_KEY not in app.session_state
    assert reconciliation_preview.ERROR_KEY not in app.session_state
    assert ("document_preview" in app.session_state) is not fails
    process.assert_called_once_with(b"pdf", "asset.pdf")
    run.assert_not_called()


def test_debug_json_is_optional_and_no_analysis_means_no_reconcile_button():
    app = AppTest.from_string(
        "from app.web.document_preview import render_document_analysis\n"
        "render_document_analysis()\n"
    ).run()
    assert not app.exception
    assert not any(button.label == "Egyeztetés az adatbázissal" for button in app.button)
    for debug, expected_json_count in ((False, 2), (True, 3)):
        app = app_with_analysis(debug=debug)
        app.session_state[reconciliation_preview.RESULT_KEY] = reconciliation()
        app.run()
        assert not app.exception
        assert len(app.json) == expected_json_count


def test_reconciliation_results_are_per_session():
    first = app_with_analysis()
    first.session_state[reconciliation_preview.RESULT_KEY] = reconciliation()
    first.run()
    second = app_with_analysis().run()
    assert not first.exception and not second.exception
    assert reconciliation_preview.RESULT_KEY not in second.session_state
    assert not any(element.value == MatchStatus.EXACT_MATCH.value for element in second.caption)
