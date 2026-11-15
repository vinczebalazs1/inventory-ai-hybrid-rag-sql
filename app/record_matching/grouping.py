"""Conservative source-based grouping. No database values enter this step."""
from collections import defaultdict
import re

from app.document_processing.models import MappingResult, ProcessingResult
from app.document_processing.provenance import spans
from .normalization import identifier_key


def _contains(text: str, identifier: str) -> bool:
    return bool(re.search(r"(?<![\w-])" + re.escape(identifier) + r"(?![\w-])", text))


def group_document(result: ProcessingResult) -> tuple[list[ProcessingResult], list, list[str]]:
    """One group per explicit physical ID; ambiguous occurrences stay unassigned.

    A unique page anchor or a verified row/card context can assign attributes.
    Multiple identifiers on a page never use nearest-value guessing.
    """
    fields = [f.model_copy(deep=True) for f in result.mapping.mapped_fields]
    anchors = [f for f in fields if f.target_field == "inventory_number" and
               f.normalized_value not in (None, "") and not f.extraction_uncertain]
    identifiers = sorted({identifier_key(str(f.normalized_value)) for f in anchors})
    by_page = defaultdict(set)
    for f in anchors:
        source = result.parsed_document.pages.get(f.page, result.parsed_document.extraction_text)
        if f.evidence and spans(source, f.evidence) and _contains(f.evidence, str(f.normalized_value)):
            by_page[f.page].add(identifier_key(str(f.normalized_value)))
    assignments = defaultdict(list)
    unassigned = []
    reasons = []
    if len(identifiers) <= 1:
        assignments[identifiers[0] if identifiers else "unidentified"] = fields
    else:
        for f in fields:
            source = result.parsed_document.pages.get(f.page, result.parsed_document.extraction_text)
            support = f.context if spans(source, f.context) and spans(f.context, f.evidence) else f.evidence
            ids = {v for v in identifiers if support and spans(source, support) and _contains(support, v)}
            if not ids and f.evidence:
                # Whole Markdown rows retain their own explicit ID. Do not use
                # a table header, another row or a preceding asset's ID.
                rows = [line for line in source.splitlines() if "|" in line and spans(line, f.evidence)]
                if f.source_span:
                    start, end = f.source_span
                    if 0 <= start < end <= len(source) and spans(source[start:end], f.evidence):
                        line = source[source.rfind('\n',0,start)+1:source.find('\n',end) if '\n' in source[end:] else len(source)]
                        if '|' in line:
                            rows = [line]
                if len(rows) == 1:
                    ids = {v for v in identifiers if _contains(rows[0], v)}
            if not ids and len(by_page[f.page]) == 1:
                ids = by_page[f.page]
            if len(ids) == 1:
                assignments[next(iter(ids))].append(f)
            else:
                unassigned.append(f)
        # Keep every anchor even when its evidence was insufficient. Such a group
        # cannot be accepted without evidence by preparation/suggestion rules.
        for identifier in identifiers:
            assignments.setdefault(identifier, [])
        if unassigned:
            reasons.append("Egyes mezőelőfordulásokhoz nincs egyértelmű sor-/oldal-/kártyaszintű eszközkapcsolat.")
    groups = []
    for key, members in sorted(assignments.items()):
        group_id = "inventory:" + key if key != "unidentified" else "unidentified:1"
        for index, f in enumerate(members):
            f.asset_group_id = group_id
            f.occurrence_id = f.occurrence_id or f"{group_id}:field-{index + 1}"
        # Parser/extraction are read-only here; avoid copying the full PDF and
        # native OCR cells once per asset. Only assigned occurrences are copied.
        group = result.model_copy()
        group.mapping = MappingResult(mapped_fields=members, unmapped_fields=list(result.mapping.unmapped_fields))
        member_ids = {f.occurrence_id for f in members}
        member_targets = {f.target_field for f in members}
        group.validation_issues = [i for i in result.validation_issues if
                                   (i.occurrence_id in member_ids if i.occurrence_id else i.field in member_targets)]
        # Preserve full parser data for evidence, but don't re-run cross-asset
        # flat-list guards on already separated groups (flag passed by caller).
        groups.append(group)
    return groups, unassigned, reasons
