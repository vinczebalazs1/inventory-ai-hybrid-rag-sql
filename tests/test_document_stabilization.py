"""2026-11 stabilization contract: user-supplied references, no external API.

These are deterministic field-level tests, not claims of running absent T01–T15
original PDFs. Real parser tests are separately opt-in below.
"""
from copy import deepcopy
import csv
import io
import json
from pathlib import Path
from unittest.mock import Mock

import pytest

from app.document_processing.models import ExtractedField, ExtractionResult, MappedField, MappingResult, ParsedDocument, ProcessingResult
from app.document_processing.validation_service import normalize, validate_fields
from app.evaluation.dataset import EvaluationCase, ExpectedOutcome, FixtureRecord
from app.evaluation.runner import FixtureRepository
from app.record_matching.config import MatchingSettings
from app.record_matching.models import ActionType as A, ComparisonStatus as C, MatchStatus as S, ReconciliationResult
from app.record_matching.reconciliation_service import reconcile_document
from app.services.schema_service import load_schema
from app.web.document_exports import csv_bytes, reconciliation_rows

COLUMNS = {c['column']: c['type'] for c in load_schema()['inventory_items']}
NAMES = {'LAT5540': 'Dell Latitude 5540', 'LAT5550': 'Dell Latitude 5550',
         'T14G4': 'Lenovo ThinkPad T14 Gen 4', 'EB840G10': 'HP EliteBook 840 G10',
         'PB450G10': 'HP ProBook 450 G10'}
# Transcribed from the user's reference table, never from a predicted result.
REFERENCE = [
    ('LAT5540','2024-01-23',417000,224151,192849,'LIB'),
    ('LAT5550','2025-10-08',522000,102111,419889,'LIB'),
    ('T14G4','2024-05-29',514000,240523,273477,'LIB'),
    ('EB840G10','2024-09-02',571000,237160,333840,'LIB'),
    ('PB450G10','2023-11-24',425000,242424,182576,'KGK'),
    ('LAT5540','2026-06-28',506000,26062,479938,'KGK'),
    ('LAT5550','2024-12-15',478000,171294,306706,'BARK'),
    ('T14G4','2025-01-03',583000,202852,380148,'KANDÓ'),
    ('EB840G10','2024-09-22',575000,232520,342480,'LIB'),
    ('PB450G10','2023-10-23',328000,192846,135154,'NIK'),
    ('LAT5540','2025-04-07',422000,125096,296904,'LIB'),
    ('LAT5550','2024-09-06',414000,171044,242956,'KANDÓ'),
    ('T14G4','2025-04-05',474000,141031,332969,'BARK'),
    ('EB840G10','2025-09-18',564000,116508,447492,'BARK'),
    ('PB450G10','2024-04-18',337000,165268,171732,'KGK'),
    ('LAT5540','2024-11-17',510000,190586,319414,'KANDÓ'),
]
ROWS = [dict(item_code=code, sub_code=0, activation_date=date, name=NAMES[code],
             purchase_value=p, depreciation=d, current_value=c, currency='HUF', quantity=1,
             inventory_number=f'L-{21+i:05}', location=loc)
        for i,(code,date,p,d,c,loc) in enumerate(REFERENCE)]


def repository(rows=None):
    case = EvaluationCase(id='stabilization', split='test', category='regression',
        description='User supplied reference records; simulated SQL reads', document_fields=[],
        records=[FixtureRecord(record_id=str(i), values=row) for i,row in enumerate(rows or ROWS)],
        unique_keys=[['inventory_number']],
        expected=ExpectedOutcome(record_ids=[], match_status='unused', actions=[], review_required=True))
    return FixtureRepository(case)


def document(*pages):
    """Each page contains one or more explicitly delimited asset cards."""
    fields, texts = [], {}
    for page, cards in enumerate(pages, 1):
        if isinstance(cards, dict):
            cards = [cards]
        contexts = ['\n'.join(f'{k}: {v}' for k,v in card.items()) for card in cards]
        texts[page] = '\n\n'.join(contexts)
        for card, context in zip(cards, contexts):
            for name,value in card.items():
                fields.append(MappedField(source_label=name, target_field=name, raw_value=str(value),
                    evidence=f'{name}: {value}', context=context, page=page))
    mapping = MappingResult(mapped_fields=fields)
    issues = validate_fields(mapping, [{'column':k,'type':v} for k,v in COLUMNS.items()])
    text = '\n\n'.join(texts.values())
    return ProcessingResult(parsed_document=ParsedDocument(source_name='contract.pdf', source_extension='.pdf',
        markdown=text, extraction_text=text, pages=texts),
        extraction=ExtractionResult(source_name='contract.pdf', fields=[]), mapping=mapping, validation_issues=issues)


def scenario(number):
    index = number-1 if number <= 13 else number
    row = deepcopy(ROWS[index])
    if number == 2:
        return document(row, row, {'inventory_number':row['inventory_number'], 'location':row['location']})
    if number == 3:
        row['location']='NIK'
        return document(row, {'inventory_number':row['inventory_number'], 'location':'NIK'})
    if number == 4:
        row.update(purchase_value=591000, current_value=353840)
    if number == 5:
        del row['inventory_number']
        row['quantity']='1 db'
    if number == 6: row['activation_date']='nem ismert'
    if number == 7: row['depreciation']=-171294
    if number == 8: row['activation_date']='2025-13-40'
    if number == 9:
        row.update(purchase_value='575 000 Ft', depreciation='232\u00a0520 Ft', current_value='342 480 HUF', activation_date='2024.09.22.')
    if number == 10: row['inventory_number']='L-0003O'
    if number == 11: row.update(item_code='LAT5550', name='Dell Latitude 5550')
    if number == 12: row['inventory_number']='L-99999'
    if number == 13: return document([ROWS[12], ROWS[13]])
    if number == 14: return document(row, {}, {'inventory_number':row['inventory_number'], 'location':'NIK'})
    if number == 15: row['name']='DellLatitude5540'
    return document(row)


@pytest.mark.parametrize('number', range(1,16), ids=lambda n:f'T{n:02}')
def test_user_stabilization_contract(number):
    source = scenario(number)
    before = source.model_dump_json()
    result = reconcile_document(source, repository=repository(), columns=COLUMNS)
    assert source.model_dump_json() == before  # No DB-to-document backfill.
    assert result.match_status != S.ERROR
    assert ReconciliationResult.model_validate_json(result.model_dump_json()) == result
    assert all(not a.executable for a in result.suggested_actions)
    if number in (1,2,3,4,6,7,8,9,15):
        assert result.match_status == S.EXACT_MATCH
        expected_id = ROWS[number-1 if number <= 13 else number]['inventory_number']
        assert result.matched_record.values['inventory_number'] == expected_id
        assert result.asset_group_count == 1
        expected_diffs = {3:1,4:2,7:1}.get(number,0)
        assert result.counts.unique_differing_fields == expected_diffs
        assert result.counts.differing_occurrences == (2 if number == 3 else expected_diffs)
    if number in (1,2,9,15):
        assert not source.validation_issues and not result.review_required
        assert [a.action_type for a in result.suggested_actions] == [A.ATTACH_DOCUMENT]
    if number == 2:
        assert result.counts.occurrences == 24 and result.counts.equal_occurrences == 24
    if number in (3,4):
        update = next(a for a in result.suggested_actions if a.action_type == A.UPDATE_CANDIDATE)
        assert update.review_required and len(update.affected_fields) == (1 if number == 3 else 2)
        assert update.changes and all(c.evidence for c in update.changes)
        assert not result.prepared_document.business_warnings
    if number in (5,10,12):
        assert result.match_status != S.EXACT_MATCH and result.review_required
        assert A.ATTACH_DOCUMENT not in [a.action_type for a in result.suggested_actions]
        assert not result.search_metadata.identity_verified
        if number == 5: assert 'inventory_number' not in result.prepared_document.values
        else:
            assert result.search_metadata.inventory_lookup.matching_rows == 0
            assert any(c.similarity_score > 0 for c in result.candidates)
    if number == 6:
        assert result.prepared_document.values['sub_code'] == 0
        assert result.counts.missing_or_unknown_occurrences == 1
        assert next(f for f in result.prepared_document.fields if f.target_field=='activation_date').validation_status == 'EXPLICIT_UNKNOWN'
    if number == 7:
        assert result.prepared_document.values['depreciation'] == -171294
        assert result.prepared_document.business_warnings
        assert result.review_required and A.ATTACH_DOCUMENT not in [a.action_type for a in result.suggested_actions]
    if number == 8:
        assert result.counts.invalid_occurrences == 1
        assert next(f for f in result.prepared_document.fields if f.target_field=='activation_date').raw_value == '2025-13-40'
    if number == 11:
        assert result.match_status == S.CONFLICTING_DATA
        assert result.identified_record.values['inventory_number'] == 'L-00031'
        assert result.critical_conflict_fields == ['item_code','name']
        assert result.counts.unique_differing_fields == 2
        assert not result.search_metadata.fuzzy_search.attempted
        assert [a.action_type for a in result.suggested_actions] == [A.MANUAL_REVIEW]
    if number == 13:
        assert result.match_status == S.MULTIPLE_ASSETS and result.asset_group_count == 2
        assert not result.unassigned_fields
        assert {g.matched_record.values['inventory_number'] for g in result.group_results} == {'L-00033','L-00034'}
        assert all(g.match_status == S.EXACT_MATCH and g.counts.unique_differing_fields == 0 for g in result.group_results)
        assert result.counts.internal_conflict_fields == 0
    if number == 14:
        assert result.match_status == S.CONFLICTING_DATA and result.asset_group_count == 1
        assert result.identified_record.values['inventory_number'] == 'L-00035'
        assert result.counts.internal_conflict_fields == 1 and result.counts.unique_differing_fields == 0
        conflicts = [c for c in result.field_comparisons if c.status == C.INTERNAL_CONFLICT]
        assert {(c.page,c.raw_document_value) for c in conflicts} == {(1,'KGK'),(3,'NIK')}
        assert 'location' not in result.prepared_document.values


@pytest.mark.parametrize('raw,expected', [('1',1),('1 db',1),('1db',1),('1 darab',1),('1\u00a0db',1),('0',0),('0 db',0)])
def test_quantities(raw,expected):
    assert normalize(raw,'integer','quantity') == expected


@pytest.mark.parametrize('space',[' ','\u00a0','\u202f','\u2009'])
@pytest.mark.parametrize('unit',['Ft','HUF'])
@pytest.mark.parametrize('sign',['','-','−'])
def test_money_unicode_spaces_signs_and_units(space,unit,sign):
    assert normalize(f'{sign}575{space}000{space}{unit}','integer','purchase_value') == (-575000 if sign else 575000)


@pytest.mark.parametrize('raw',['57 50 00 Ft','575  000 HUF','1,234','1.234','5O0 Ft','575\t000 Ft','NaN','1e3','1 db extra','1.5 db'])
def test_bad_numbers_are_not_repaired(raw):
    with pytest.raises(ValueError): normalize(raw,'integer','quantity' if 'db' in raw else 'purchase_value')


@pytest.mark.parametrize('raw',['2024-09-22','2024.09.22.','2024. 09. 22.'])
def test_dates(raw):
    assert normalize(raw,'date','activation_date') == '2024-09-22'


def test_invalid_occurrence_does_not_poison_other_occurrences():
    source = document(ROWS[0], {'inventory_number':'L-00021','activation_date':'2025-13-40'})
    result = reconcile_document(source, repository=repository(), columns=COLUMNS)
    dates=[c for c in result.field_comparisons if c.field=='activation_date']
    assert [c.status for c in dates] == [C.EQUAL,C.INVALID]
    assert result.match_status == S.EXACT_MATCH and result.review_required


def test_zero_unknown_missing_and_unparseable_are_distinct():
    result = document({'sub_code':0,'quantity':'0 db','activation_date':'nem ismert','location':'NULL','purchase_value':'oops'})
    fields={f.target_field:f for f in result.mapping.mapped_fields}
    assert fields['sub_code'].normalized_value == fields['quantity'].normalized_value == 0
    assert fields['activation_date'].normalization_status == 'EXPLICIT_UNKNOWN'
    assert fields['location'].normalization_status == 'MISSING'
    assert fields['purchase_value'].normalization_status == 'UNPARSEABLE'


@pytest.mark.parametrize('same_page',[False,True])
def test_same_model_separate_inventory_ids_never_merge(same_page):
    a,b=ROWS[0],ROWS[5]
    source=document([a,b]) if same_page else document(a,b)
    result=reconcile_document(source,repository=repository(),columns=COLUMNS)
    assert result.asset_group_count==2 and not result.unassigned_fields
    assert all(g.match_status==S.EXACT_MATCH for g in result.group_results)


def test_unassigned_field_stays_visible_and_blocks_acceptance():
    source=document([ROWS[12],ROWS[13]])
    field=MappedField(source_label='location',target_field='location',raw_value='LIB',evidence='Unassigned location: LIB',page=1)
    source.mapping.mapped_fields.append(field)
    source.parsed_document.pages[1]+='\n\nUnassigned location: LIB'
    validate_fields(source.mapping,[{'column':k,'type':v} for k,v in COLUMNS.items()])
    result=reconcile_document(source,repository=repository(),columns=COLUMNS)
    assert len(result.unassigned_fields)==1 and result.review_required
    assert result.counts.occurrences==23 and result.counts.unassigned_occurrences==1
    assert all(a.action_type==A.MANUAL_REVIEW for g in result.group_results for a in g.suggested_actions)
    assert reconciliation_rows(result,'fields')[-1]['grouping_status']=='UNASSIGNED'


def test_uncertain_ocr_never_produces_proven_difference_or_update():
    source=scenario(15)
    field=next(f for f in source.mapping.mapped_fields if f.target_field=='purchase_value')
    field.raw_value='510080'; field.normalized_value=510080
    field.extraction_method='ocr'; field.extraction_uncertain=True; field.recognition_confidence=0.67
    field.uncertainty_reason='OCR recognition below threshold'
    result=reconcile_document(source,repository=repository(),columns=COLUMNS)
    assert result.match_status==S.EXACT_MATCH and result.review_required
    assert result.counts.unique_differing_fields==0 and result.counts.uncertain_occurrences>=1
    assert next(c for c in result.field_comparisons if c.field=='purchase_value').status==C.UNCERTAIN
    assert all(a.action_type==A.MANUAL_REVIEW for a in result.suggested_actions)


def test_csv_contains_occurrences_groups_and_deduplicated_differences():
    result=reconcile_document(scenario(3),repository=repository(),columns=COLUMNS)
    records=list(csv.DictReader(io.StringIO(csv_bytes(reconciliation_rows(result,'comparisons')).decode('utf-8-sig'))))
    diffs=[r for r in records if r['status']=='DIFFERENT']
    assert len(diffs)==2 and {r['field'] for r in diffs}=={'location'}
    assert {r['page'] for r in diffs}=={'1','2'} and all(r['asset_group_id']=='inventory:L-00023' for r in diffs)
    assert "'=SUM" in csv_bytes([{'text':'=SUM(A1:A2)'}]).decode('utf-8-sig')


def test_thousands_of_records_cannot_hide_conflicting_primary_hit():
    row=ROWS[10]
    rows=[dict(row,inventory_number=f'X-{i}') for i in range(4000)]+[row]
    result=reconcile_document(scenario(11),repository=repository(rows),columns=COLUMNS,
                              settings=MatchingSettings(max_candidates=1,max_scan_rows=1))
    assert result.match_status==S.CONFLICTING_DATA and result.identified_record.values==row
    assert result.search_metadata.scanned_rows==1 and result.search_metadata.inventory_lookup.complete
    assert not result.search_metadata.fuzzy_search.attempted


def test_ranking_retains_relevance_for_conflicting_inventory_candidates():
    source=scenario(10)
    result=reconcile_document(source,repository=repository(),columns=COLUMNS)
    assert result.candidates[0].values['inventory_number']=='L-00030'
    assert result.candidates[0].similarity_score>0
    assert result.review_required and result.match_status!=S.EXACT_MATCH


def test_streamlit_internal_conflict_and_multiasset_results(monkeypatch):
    from streamlit.testing.v1 import AppTest
    from app.web import reconciliation_preview as ui
    for number in (11,13,14):
        result=reconcile_document(scenario(number),repository=repository(),columns=COLUMNS)
        monkeypatch.setattr(ui,'_run_reconciliation',lambda _source:result)
        app=AppTest.from_string('from app.web.document_preview import render_document_analysis\nrender_document_analysis()')
        app.session_state['document_preview']=scenario(number)
        app.run().button(key='reconcile_document').click().run()
        assert not app.exception
        if number==13: assert any('Eszközcsoportok száma: 2' in c.value for c in app.caption)
        if number==14: assert any('Dokumentumon belüli ellentmondás' in c.value for c in app.warning)


def test_short_source_values_never_match_inside_other_numbers():
    from app.document_processing.provenance import spans
    assert len(spans('0 510000 L-00010 0','0'))==2
    assert not spans('L-00030','L-0003')


@pytest.mark.parametrize('label,target', [('Tételkód','item_code'),('Altételkód','sub_code'),
    ('Eszköz neve','name'),('Helyazonosító','location'),('Nyilvántartott hely','location'),
    ('Bekerülési érték','purchase_value'),('Elszámolt értékcsökkenés','depreciation'),
    ('Nettó könyv szerinti érték','current_value'),('inventory id','inventory_number')])
def test_explicit_aliases(label,target):
    from app.document_processing.field_labels import canonical_label
    assert canonical_label(label)==target


def test_location_label_is_removed_only_for_explicit_code_suffix():
    assert normalize('KGK location','text','location')=='KGK'
    assert normalize('KANDÓ','text','location')=='KANDÓ'
    assert normalize('New location','text','location')=='New location'
    assert normalize('KGK location','text','name')=='KGK location'


def test_high_confidence_ocr_difference_still_needs_image_verification():
    source=document(dict(ROWS[0],location='KANDO'))
    field=next(f for f in source.mapping.mapped_fields if f.target_field=='location')
    field.extraction_method='ocr'; field.recognition_confidence=0.99
    result=reconcile_document(source,repository=repository(),columns=COLUMNS)
    assert result.counts.uncertain_occurrences==1 and result.counts.unique_differing_fields==0
    assert result.review_required
    assert all(a.action_type==A.MANUAL_REVIEW for a in result.suggested_actions)
