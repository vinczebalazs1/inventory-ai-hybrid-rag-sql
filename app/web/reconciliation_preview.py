"""Read-only reconciliation controls and presentation for an existing analysis."""
import logging

import streamlit as st

from app.document_processing.models import ProcessingResult
from app.record_matching.models import (
    ActionType, CandidateRecord, ComparisonStatus, MatchStatus, ReconciliationResult,
)

logger = logging.getLogger(__name__)
from .document_exports import csv_bytes, reconciliation_rows

RESULT_KEY = "document_reconciliation"
ERROR_KEY = "document_reconciliation_error"

STATUS_LABELS = {
    MatchStatus.EXACT_MATCH: "Pontos azonosítóegyezés",
    MatchStatus.LIKELY_MATCH: "Valószínű egyezés",
    MatchStatus.AMBIGUOUS_MATCH: "Több lehetséges egyezés",
    MatchStatus.NO_MATCH: "Nincs megfelelő találat az elvégzett keresésben",
    MatchStatus.INSUFFICIENT_DATA: "Nincs elegendő használható adat",
    MatchStatus.CONFLICTING_DATA: "Ellentmondó adatok",
    MatchStatus.SEARCH_INCOMPLETE: "A keresés nem teljes",
    MatchStatus.ERROR: "Egyeztetési hiba",
    MatchStatus.MULTIPLE_ASSETS: "Több külön eszköz, csoportonkénti eredmények",
}
ACTION_LABELS = {
    ActionType.ATTACH_DOCUMENT: "Dokumentumcsatolás javaslata",
    ActionType.UPDATE_CANDIDATE: "Rekordfrissítés javaslata",
    ActionType.CREATE_RECORD_CANDIDATE: "Új rekord javaslata",
    ActionType.MANUAL_REVIEW: "Emberi ellenőrzés szükséges",
}
FIELD_LABELS = {"inventory_number": "Leltári szám", "item_code": "Cikkszám", "sub_code": "Alszám",
                "name": "Eszköznév", "location": "Helyszín", "activation_date": "Aktiválás dátuma",
                "quantity": "Mennyiség", "currency": "Pénznem", "purchase_value": "Beszerzési érték",
                "depreciation": "Értékcsökkenés", "current_value": "Jelenlegi érték"}
STRATEGY_LABELS = {"inventory_number_exact": "Pontos leltáriszám-egyezés",
                  "inventory_number_unverified": "Leltári szám egyezik, egyediség nem igazolt",
                  "exact_identifier": "Pontos másodlagos azonosítóegyezés",
                  "unverified_identifier": "Azonosítóérték egyezik, egyediség nem igazolt",
                  "composite_identifier": "Cikkszám és alszám egyezése",
                  "composite_fields": "Több leíró mező egyezése",
                  "fuzzy_name": "Hasonló eszköznév", "weighted_fields": "Mezők súlyozott egyezése"}
COMPARISON_LABELS = {ComparisonStatus.EQUAL: "Egyezik", ComparisonStatus.DIFFERENT: "Eltér",
                     ComparisonStatus.UNKNOWN: "Ismeretlen", ComparisonStatus.INVALID: "Hibás adat",
                     ComparisonStatus.NOT_COMPARABLE: "Nem összehasonlítható"}
COMPARISON_LABELS.update({ComparisonStatus.INTERNAL_CONFLICT: "Belső ellentmondás",
                          ComparisonStatus.UNCERTAIN: "Bizonytalan kinyerés"})


def clear_reconciliation() -> None:
    """Invalidate both successful and failed runs when the analysis changes."""
    st.session_state.pop(RESULT_KEY, None)
    st.session_state.pop(ERROR_KEY, None)


def _run_reconciliation(processing_result: ProcessingResult) -> ReconciliationResult:
    # Keep startup independent of database initialization and configuration.
    from app.record_matching.reconciliation_service import reconcile_document

    return reconcile_document(processing_result)


def _value(value: object) -> str:
    """Keep mixed nullable/numeric values readable in Streamlit table columns."""
    return "—" if value is None else str(value)


def _render_candidates(candidates: list[CandidateRecord], show_debug: bool = False) -> None:
    st.subheader("Rangsorolt rekordjelöltek")
    if not candidates:
        st.caption("Nincs megjeleníthető rekordjelölt.")
        return
    relevant_fields = [
        field for field in ("inventory_number", "item_code", "sub_code", "name", "location")
        if any(field in candidate.values for candidate in candidates)
    ]
    rows = []
    for candidate in candidates:
        row = {"Rang": candidate.rank}
        row.update({FIELD_LABELS[field]: _value(candidate.values.get(field)) for field in relevant_fields})
        row.update({
            "Hasonlósági pontszám": candidate.similarity_score,
            "Egyeztetés alapja": STRATEGY_LABELS.get(candidate.strategy, "Mezőegyeztetés"),
            "Egyedi kulcs értéke egyezik": candidate.verified_identifier_match,
            "Ellenőrzés szükséges": candidate.review_required,
        })
        if show_debug:
            row.update({"strategy": candidate.strategy, "record_id": _value(candidate.record_id)})
        rows.append(row)
    st.dataframe(rows, use_container_width=True, hide_index=True)

    with st.expander("Pontozás és egyezési indokok"):
        for candidate in candidates:
            st.text(f"{candidate.rank}. jelölt – {candidate.similarity_score:.3f} pont")
            if not candidate.record_id:
                st.warning("Ehhez a jelölthöz nem igazolt stabil rekordazonosító.")
            if candidate.matching_fields:
                st.text("Egyező mezők: " + ", ".join(FIELD_LABELS.get(f, f) for f in candidate.matching_fields))
            for reason in candidate.reasons:
                st.text(reason)
            if candidate.identifier_conflicts:
                st.warning("Azonosítóellentmondás található.")
                for conflict in candidate.identifier_conflicts:
                    st.text(conflict)
            for warning in candidate.warnings:
                st.text(warning)
            if candidate.score_breakdown:
                st.dataframe([
                    {
                        "Mező": FIELD_LABELS.get(part.field, part.field),
                        "Hasonlóság": part.similarity,
                        "Súly": part.weight,
                        "Hozzájárulás": part.contribution,
                        "Indok": part.explanation,
                    }
                    for part in candidate.score_breakdown
                ], use_container_width=True, hide_index=True)


def _render_comparisons(result: ReconciliationResult) -> None:
    st.subheader("Mezőösszehasonlítás és eltérések")
    if not result.field_comparisons:
        st.caption("Ehhez az eredményhez nincs mezőszintű összehasonlítás.")
        return
    differences = sum(
        comparison.status == ComparisonStatus.DIFFERENT
        for comparison in result.field_comparisons
    )
    unique = len({comparison.field for comparison in result.field_comparisons
                  if comparison.status == ComparisonStatus.DIFFERENT})
    st.caption(f"Eltérő mezőelőfordulások: {differences} · Egyedi eltérő mezők: {unique}")
    st.dataframe([
        {
            "Jelölt": comparison.candidate_rank,
            "Eszközcsoport": _value(comparison.asset_group_id),
            "Előfordulás": _value(comparison.occurrence_id),
            "Mező": FIELD_LABELS.get(comparison.field, comparison.field),
            "Eltérés": comparison.status == ComparisonStatus.DIFFERENT,
            "Forráscímke": _value(comparison.source_label),
            "Dokumentum – eredeti": _value(comparison.raw_document_value),
            "Dokumentum – normalizált": _value(comparison.normalized_document_value),
            "Adatbázis": _value(comparison.database_value),
            "Státusz": COMPARISON_LABELS[comparison.status],
            "Bizonyíték": _value(comparison.evidence),
            "Oldal": _value(comparison.page),
            "Validáció": _value(comparison.validation_status),
            "Kinyerés": comparison.extraction_method,
            "Felismerési pontszám": _value(comparison.recognition_confidence),
            "Magyarázat": comparison.explanation,
        }
        for comparison in result.field_comparisons
    ], use_container_width=True, hide_index=True)


def _render_actions(result: ReconciliationResult) -> None:
    st.subheader("Javasolt műveletek")
    st.caption("Az alábbiak ellenőrizendő javaslatok. Módosítás és dokumentumcsatolás nem történt.")
    if not result.suggested_actions:
        st.caption("Nincs műveleti javaslat.")
    for action in result.suggested_actions:
        st.markdown(f"**{ACTION_LABELS[action.action_type]}**")
        st.text(action.reason)
        if action.candidate_rank:
            st.text(f"Érintett jelölt: {action.candidate_rank}.")
        if action.action_type == ActionType.UPDATE_CANDIDATE and not action.target_identity_verified:
            st.warning("A célrekord azonossága még nem igazolt; ez csak ellenőrizendő lehetőség.")
        if action.review_required:
            st.warning("Emberi ellenőrzés szükséges a javaslat értékeléséhez.")
        for label, fields in (
            ("Érintett mezők", action.affected_fields),
            ("Rendelkezésre álló mezők", action.available_fields),
            ("Hiányzó mezők", action.missing_fields),
        ):
            if fields:
                st.text(label + ": " + ", ".join(FIELD_LABELS.get(f, f) for f in fields))
        for limitation in action.limitations:
            st.text(limitation)


def _render_result(result: ReconciliationResult, show_debug: bool) -> None:
    st.subheader("Egyeztetési összefoglaló")
    if result.group_results:
        st.write(STATUS_LABELS[result.match_status])
        st.caption(f"Eszközcsoportok száma: {result.asset_group_count}")
        st.caption(f"Összes eltérő előfordulás: {result.counts.differing_occurrences}; "
                   f"egyedi csoport–mező eltérés: {result.counts.unique_differing_fields}")
        for group in result.group_results:
            with st.expander("Eszköz: " + (group.asset_group_id or "nem azonosított"), expanded=True):
                _render_result(group, show_debug)
        if result.unassigned_fields:
            st.warning("Nem hozzárendelhető mezők; emberi ellenőrzés szükséges.")
            st.dataframe([f.model_dump(mode="json") for f in result.unassigned_fields], hide_index=True)
        return
    st.caption("Eszközcsoport: " + (result.asset_group_id or "nem azonosított"))
    primary_exact = (result.match_status == MatchStatus.EXACT_MATCH and result.matched_record
                     and result.matched_record.strategy == "inventory_number_exact")
    st.write("Pontos leltáriszám-egyezés" if primary_exact else STATUS_LABELS[result.match_status])
    if show_debug:
        st.caption(result.match_status.value)
    if result.prepared_document and result.prepared_document.values.get("inventory_number"):
        st.text("Leltári szám: " + str(result.prepared_document.values["inventory_number"]))
    schema = result.search_metadata.schema_info
    if schema and schema.verified and schema.compatible and ["inventory_number"] in schema.unique_keys:
        st.caption("A leltári szám egyediségét az adatbázis garantálja. NULL érték alapján nincs azonosítás.")
    else:
        st.caption("A leltári szám egyedisége nincs adatbázis-kulccsal igazolva; a találatok kézzel ellenőrizhetők.")
    if result.review_required:
        st.warning("Az eredmény emberi ellenőrzést igényel.")
    else:
        st.success("Az egyeztetés nem jelzett további ellenőrzési igényt.")
    if result.identified_record:
        st.text("Leltári szám alapján azonosított rekord: " + str(result.identified_record.values.get("inventory_number")))
        st.caption("Azonosítás típusa: pontos azonosító-találat. A mezőkonfliktus ettől külön vizsgált.")
    if result.critical_conflict_fields:
        st.warning("Kritikus mezőkonfliktus: " + ", ".join(result.critical_conflict_fields) + ". Automatikus elfogadás nincs.")
    if result.prepared_document:
        if result.prepared_document.internal_conflicts:
            st.warning("Dokumentumon belüli ellentmondás: " + ", ".join(result.prepared_document.internal_conflicts))
        with st.expander("Eszközcsoport mezői és validáció"):
            st.dataframe([{**f.model_dump(mode="json"), "normalized_value": _value(f.normalized_value),
                           "comparison_value": _value(f.comparison_value)} for f in result.prepared_document.fields], hide_index=True)
        st.caption(f"Előfordulások: {result.counts.occurrences}; normalizált: {result.counts.normalized_occurrences}; "
                   f"hibás: {result.counts.invalid_occurrences}; hiányzó/ismeretlen: {result.counts.missing_or_unknown_occurrences}; "
                   f"bizonytalan kinyerés: {result.counts.uncertain_occurrences}")
    for reason in result.reasons:
        st.text(reason)
    if not result.search_metadata.complete:
        st.warning("A keresés nem teljes. Ebből nem állapítható meg, hogy egy rekord nem létezik.")
    if result.search_metadata.fuzzy_search.skipped_reason == "verified_inventory_lookup":
        st.caption("A célzott leltáriszám-keresés befejeződött. Teljes táblás névkeresésre nem volt szükség.")
    for warning in dict.fromkeys(result.warnings + result.search_metadata.warnings):
        st.text(warning)
    if result.candidates:
        best = result.candidates[0]
        st.text("Legjobb jelölt: " + _value(best.values.get("name") or best.record_id))
        score_column, strategy_column = st.columns(2)
        score_column.metric("Hasonlósági pontszám", f"{best.similarity_score:.3f}")
        strategy_column.metric("Egyeztetés alapja", STRATEGY_LABELS.get(best.strategy, "Mezőegyeztetés"))
    st.caption("A 0–1 közötti pontszám rangsorolási érték, nem kalibrált valószínűség.")
    _render_candidates(result.candidates, show_debug)
    _render_comparisons(result)
    _render_actions(result)
    if show_debug:
        with st.expander("Egyeztetés – technikai részletek"):
            st.json(result.model_dump(mode="json"))


def render_reconciliation(processing_result: ProcessingResult, show_debug: bool = False) -> None:
    """Run only on an explicit click; preserve analysis even when reconciliation fails."""
    st.divider()
    st.subheader("Rekordegyeztetés")
    if st.button("Egyeztetés az adatbázissal", key="reconcile_document"):
        clear_reconciliation()
        with st.spinner("Leltárrekordok keresése és összehasonlítása…"):
            try:
                st.session_state[RESULT_KEY] = _run_reconciliation(processing_result)
            except Exception as exc:
                # Exceptions may contain DSNs, SQL parameters or document text.
                # Neither normal UI nor debug output receives the exception text.
                error_type = type(exc).__name__
                logger.warning("Reconciliation UI failed: %s", error_type)
                st.session_state[ERROR_KEY] = error_type
    error_type = st.session_state.get(ERROR_KEY)
    if error_type:
        st.error("Az egyeztetés sikertelen. A dokumentumelemzés megmaradt; ellenőrizd az adatbázis elérését és a beállításokat.")
        if show_debug:
            st.caption("Egyeztetési hibakategória: " + error_type)
    result = st.session_state.get(RESULT_KEY)
    if result is not None:
        _render_result(result, show_debug)
        for kind, label in (("fields", "Eszközcsoportok mezői"), ("comparisons", "Mezőösszehasonlítás"), ("candidates", "Rangsorolt rekordjelöltek")):
            rows = reconciliation_rows(result, kind)
            if rows:
                st.download_button(label + " – CSV", csv_bytes(rows), file_name=f"reconciliation_{kind}.csv",
                                   mime="text/csv", key=f"export_reconciliation_{kind}")
