"""Deterministic, missing-aware ranking with explicit vetoes and abstention."""
import json

from .candidate_service import name_similarity
from .config import IDENTIFIER_FIELDS, MatchingSettings
from .models import (CandidateRecord, CandidateSearchResult, DatabaseRecord, MatchDecision,
                     MatchStatus, PreparedDocument, SchemaInfo, ScoreContribution)
from .normalization import comparison_value, model_conflict


def stable_identity(record: DatabaseRecord, schema: SchemaInfo | None) -> bool:
    if not schema or not schema.verified or not schema.compatible or not record.record_id:
        return False
    keys = schema.unique_keys + ([schema.primary_key] if schema.primary_key else [])
    return (record.identity_fields in keys and bool(record.identity_fields)
            and all(record.values.get(name) is not None for name in record.identity_fields))


class MatchingEngine:
    def __init__(self, settings: MatchingSettings):
        self.settings = settings

    def score(self, document: PreparedDocument, record: DatabaseRecord,
              schema: SchemaInfo | None, columns: dict[str, str]) -> CandidateRecord:
        settings = self.settings
        fields = {name: value for name, value in document.values.items()
                  if name in settings.weights and value is not None}
        active = {name: value for name, value in fields.items()
                  if settings.strategy == "hybrid" or name in (*IDENTIFIER_FIELDS, "sub_code")}
        denominator = sum(settings.weights[name] for name in active)
        parts, matching, conflicts = [], [], []
        technical_conflict = False
        for name, value in active.items():
            try:
                left = comparison_value(value, columns[name], name)
                # PostgreSQL uniqueness applies to the stored identifier. Do
                # not trim/case-fold DB keys into a different unique value.
                right = (record.values.get(name) if name in IDENTIFIER_FIELDS else
                         comparison_value(record.values.get(name), columns[name], name))
            except (ValueError, TypeError):
                right, left = None, value
            similarity = float(right is not None and left == right)
            explanation = "Pontos mezőegyezés." if similarity else "Eltérő vagy hiányzó adatbázisérték."
            if name == "name" and right is not None:
                similarity = name_similarity(left, right)
                technical_conflict = model_conflict(str(left), str(right)) or similarity < settings.duplicate_threshold
                explanation = "Teljes név ratio/token_sort_ratio hasonlósága; a modellszám külön ellenőrzött."
            if name in IDENTIFIER_FIELDS and right is not None and left != right:
                conflicts.append(name)
            if similarity == 1.0:
                matching.append(name)
            weight = settings.weights[name]
            parts.append(ScoreContribution(field=name, similarity=similarity, weight=weight,
                         contribution=weight * similarity / denominator if denominator else 0.0,
                         explanation=explanation))
        # Baseline still applies the same safety vetoes to the original document.
        if settings.strategy == "exact_only" and fields.get("name") and record.values.get("name"):
            technical_conflict = (model_conflict(str(fields["name"]), str(record.values["name"])) or
                                  name_similarity(fields["name"], record.values["name"]) < settings.duplicate_threshold)
        if document.values.get("sub_code") is not None and record.values.get("sub_code") is not None:
            if document.values["sub_code"] != record.values["sub_code"] and "item_code" in matching:
                conflicts.append("sub_code")
        keys = schema.unique_keys + ([schema.primary_key] if schema.primary_key else []) if schema else []
        verified = stable_identity(record, schema) and any(
            key and set(key).issubset({*IDENTIFIER_FIELDS, "sub_code"})
            and any(name in IDENTIFIER_FIELDS for name in key)
            and all(name in matching for name in key) for key in keys
        )
        exact_id = any(name in matching for name in IDENTIFIER_FIELDS)
        score = sum(part.contribution for part in parts)
        strategy = "fuzzy_name" if "name" in active else "weighted_fields"
        reasons, warnings = [], []
        if exact_id:
            strategy = "exact_identifier" if verified else "unverified_identifier"
            score = 1.0 if verified else max(score, settings.likely_threshold)
            reasons.append("Ellenőrzött egyedi kulcs egyezik." if verified else
                           "Az azonosító értéke egyezik; önmagában nincs igazolt egyediség.")
        if "item_code" in matching and "sub_code" in matching:
            strategy = "composite_identifier"
        elif "name" in matching and any(name in matching for name in ("location", "activation_date")):
            strategy = "composite_fields" if not exact_id else strategy
        if not verified:
            # A score of 1 for a name must never look like a proven exact identity.
            score = min(score, settings.exact_threshold - 0.001)
        if conflicts:
            score = 0.0
            reasons.append("Ellentmondó azonosító: " + ", ".join(conflicts) + ".")
        if technical_conflict:
            score = min(score, settings.model_conflict_cap)
            reasons.append("Eltérő modell- vagy típusszám; a névhasonlóság nem igazolja az azonosságot.")
        if not stable_identity(record, schema):
            warnings.append("A rekordhoz nincs igazolt, stabil adatbázis-azonosító.")
        return CandidateRecord(**record.model_dump(), rank=1, similarity_score=round(min(1.0, score), 8),
                               strategy=strategy, matching_fields=matching, score_breakdown=parts,
                               identifier_conflicts=conflicts, technical_conflict=technical_conflict,
                               verified_identifier_match=verified, reasons=reasons, warnings=warnings)

    def match(self, document: PreparedDocument, search: CandidateSearchResult,
              columns: dict[str, str]) -> MatchDecision:
        if document.blocked:
            return MatchDecision(status=MatchStatus.CONFLICTING_DATA, reasons=document.reasons)
        name = str(document.values.get("name") or "")
        descriptive_name = len(name.split()) >= 2 or any(char.isdigit() for char in name)
        has_identifier = any(document.values.get(field) not in (None, "") for field in IDENTIFIER_FIELDS)
        if not has_identifier and (self.settings.strategy == "exact_only" or not descriptive_name):
            return MatchDecision(status=MatchStatus.INSUFFICIENT_DATA,
                                 reasons=["Nincs felhasználható azonosító vagy eszköznév az egyeztetéshez."])
        candidates = [self.score(document, record, search.metadata.schema_info, columns) for record in search.records]
        candidates.sort(key=lambda row: (-row.similarity_score, row.record_id or "",
                                        json.dumps(row.values, sort_keys=True, ensure_ascii=False)))
        for rank, candidate in enumerate(candidates, 1):
            candidate.rank = rank
        def decision(status, reason, selected=None, review=True):
            return MatchDecision(status=status, candidates=candidates, matched_record=selected,
                                 reasons=[reason], review_required=review)
        if (not search.metadata.complete or search.metadata.truncated or search.metadata.timed_out
                or not search.metadata.schema_info or not search.metadata.schema_info.verified
                or not search.metadata.schema_info.compatible):
            return decision(MatchStatus.SEARCH_INCOMPLETE, "A keresés teljessége vagy a séma érvényessége nem igazolt.")
        exact = [row for row in candidates if any(name in row.matching_fields for name in IDENTIFIER_FIELDS)]
        schema = search.metadata.schema_info
        composite_keys = [key for key in schema.unique_keys if set(key) == {"item_code", "sub_code"}]
        if composite_keys and "sub_code" in document.values:
            # Sibling subrecords share item_code intentionally. They are not an
            # inconsistent second observation of the selected composite identity.
            exact = [row for row in exact if "sub_code" not in row.identifier_conflicts
                     or "inventory_number" in row.matching_fields]
        if any(row.identifier_conflicts or row.technical_conflict for row in exact):
            return decision(MatchStatus.CONFLICTING_DATA, "Az azonosítóegyezés mellett kritikus adatellentmondás található.")
        # A verified composite key may disambiguate repeated item_code values.
        verified = [row for row in exact if row.verified_identifier_match]
        if len(exact) > 1 and len(verified) != 1:
            return decision(MatchStatus.AMBIGUOUS_MATCH, "Több rekord azonosítója egyezik; a név nem igazol egyediséget.")
        eligible = [row for row in candidates if not row.identifier_conflicts and not row.technical_conflict
                    and row.similarity_score >= self.settings.likely_threshold
                    and (self.settings.strategy != "exact_only" or row in exact)]
        if not eligible:
            return decision(MatchStatus.NO_MATCH, "A teljes vizsgált keresési tartományban nincs elfogadható egyezés.")
        best = eligible[0]
        if len(eligible) > 1 and best.similarity_score - eligible[1].similarity_score <= self.settings.ambiguity_margin:
            return decision(MatchStatus.AMBIGUOUS_MATCH, "A vezető jelöltek pontszáma túl közel van egymáshoz.")
        if best.verified_identifier_match and best.similarity_score >= self.settings.exact_threshold:
            clean = all(field.validation_status == "VALID" and field.evidence for field in document.fields)
            best.review_required = not clean
            return decision(MatchStatus.EXACT_MATCH, "Igazolt egyedi azonosítóegyezés, kritikus konfliktus nélkül.", best, not clean)
        return decision(MatchStatus.LIKELY_MATCH, "A legjobb jelölt hasonló; emberi rekordazonosítás szükséges.", best)
