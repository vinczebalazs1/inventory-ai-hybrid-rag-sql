"""Advisory rules only. There is deliberately no execution function."""
from .config import IDENTIFIER_FIELDS, SENSITIVE_FIELDS, MatchingSettings
from .models import (ActionType as Action, ComparisonStatus, FieldComparison, MatchDecision,
                     MatchStatus, PreparedDocument, SearchMetadata, SuggestedAction)
from .matching_engine import stable_identity
from .candidate_service import name_similarity


def suggest_actions(document: PreparedDocument, decision: MatchDecision,
                    comparisons: list[FieldComparison], search: SearchMetadata,
                    columns: dict[str, str], settings: MatchingSettings) -> list[SuggestedAction]:
    actions = []
    clean = bool(document.fields) and all(field.validation_status == "VALID" and field.evidence for field in document.fields)
    record = decision.matched_record
    if (decision.status == MatchStatus.EXACT_MATCH and record and clean
            and stable_identity(record, search.schema_info)):
        actions.append(SuggestedAction(action_type=Action.ATTACH_DOCUMENT, target_record=record.record_id,
                       reason="Igazolt egyedi rekordazonosság és visszakereshető dokumentumbizonyíték.", review_required=False))
        different = sorted({item.field for item in comparisons if item.status == ComparisonStatus.DIFFERENT})
        if different:
            sensitive = sorted(set(different) & SENSITIVE_FIELDS)
            actions.append(SuggestedAction(action_type=Action.UPDATE_CANDIDATE, target_record=record.record_id,
                           reason="Validált dokumentummezők eltérnek az azonosított rekordtól; módosítás előtt ellenőrzés szükséges.",
                           affected_fields=different,
                           limitations=["Érzékeny pénzügyi vagy azonosítómező: " + ", ".join(sensitive)] if sensitive else []))
    if (decision.status == MatchStatus.NO_MATCH and search.complete and search.scope == "full_table"
            and clean and not document.blocked and document.values.get("name")
            and any(document.values.get(name) for name in IDENTIFIER_FIELDS)
            and not any(row.similarity_score >= settings.duplicate_threshold or
                        "name" in row.matching_fields or row.identifier_conflicts
                        or name_similarity(document.values.get("name"), row.values.get("name")) >= settings.duplicate_threshold
                        for row in decision.candidates)):
        actions.append(SuggestedAction(action_type=Action.CREATE_RECORD_CANDIDATE,
                       reason="Teljes keresés után nincs elfogadható egyezés; validált név és azonosító rendelkezésre áll.",
                       available_fields=sorted(document.values), missing_fields=sorted(columns.keys() - document.values.keys()),
                       limitations=["Emberi ellenőrzés szükséges; az adatbázis kötelező üzleti mezőit külön ellenőrizni kell."]))
    limited_comparison = any(item.source_label is not None and item.status in
                             (ComparisonStatus.INVALID, ComparisonStatus.NOT_COMPARABLE) for item in comparisons)
    if decision.review_required or not clean or limited_comparison or any(action.review_required for action in actions) or not actions:
        actions.append(SuggestedAction(action_type=Action.MANUAL_REVIEW,
                       reason="; ".join(decision.reasons) or "A dokumentum és a rekordok ellenőrzése szükséges."))
    return actions
