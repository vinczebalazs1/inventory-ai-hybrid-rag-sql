"""Real local parsing + explicitly stubbed LLM, separated from field contracts."""
import hashlib
import io
import json
import os
from pathlib import Path
import re
from unittest.mock import Mock

import pytest

from app.document_processing import processing_service
from app.document_processing.docling_parser import parse_document
from app.document_processing.models import ExtractedField, ParsedDocument
from app.document_processing.provenance import ground
from app.record_matching.models import ComparisonStatus, MatchStatus
from app.record_matching.reconciliation_service import reconcile_document
from app.services import llm_service
from test_document_stabilization import COLUMNS, ROWS, document, repository


def test_grounding_ignores_llm_coordinates_and_uses_actual_ocr_score():
    parsed=ParsedDocument(source_name='scan.pdf',source_extension='.pdf',markdown='quantity: 1',extraction_text='quantity: 1',
        pages={1:'quantity: 1'},ocr_pages=[1],source_cells={1:[{'text':'1','from_ocr':True,'confidence':0.61,'rect':{'r_x0':10}}]})
    field=ExtractedField(label='quantity',value='1',evidence='quantity: 1',recognition_confidence=1.0,
                          bounding_boxes=[{'invented':True}],asset_group_id='invented',page=99)
    actual=ground(field,parsed,1,parsed.pages[1])
    assert actual.page==1 and actual.asset_group_id is None
    assert actual.recognition_confidence==0.61 and actual.extraction_uncertain
    assert actual.bounding_boxes==[{'page':1,'rect':{'r_x0':10}}]


def test_missing_ocr_confidence_is_not_invented():
    parsed=ParsedDocument(source_name='scan.pdf',source_extension='.pdf',markdown='quantity: 1',extraction_text='quantity: 1',
                           pages={1:'quantity: 1'},ocr_pages=[1])
    actual=ground(ExtractedField(label='quantity',value='1',evidence='quantity: 1'),parsed,1,parsed.pages[1])
    assert actual.recognition_confidence is None and actual.extraction_uncertain


def _labelled_stub(monkeypatch, reference, first_pages=None):
    """Manual reference assignment only if its literal value is in the parsed page.

    This deliberately does not claim to test provider extraction accuracy.
    """
    def reply(text, model):
        if 'Document chunk:\n' in text:
            page=json.loads(text.split('Parser page metadata (null means unavailable): ')[1].splitlines()[0])
            chunk=text.split('Document chunk:\n',1)[1]
            fields=[]
            for name,value in reference.items():
                if first_pages and page not in first_pages and name!='inventory_number':
                    continue
                raw=str(value)
                found=re.search(r'(?<![\w-])'+re.escape(raw)+r'(?![\w-])',chunk)
                if found:
                    fields.append({'label':name,'value':raw,'evidence':found.group(),'page':page})
            return json.dumps({'fields':fields})
        fields=json.loads(text.split('Extracted fields with indexes: ')[1])
        return json.dumps({'assignments':[{'index':f['index'],'target_field':f['label']} for f in fields]})
    mock=Mock(side_effect=reply)
    monkeypatch.setattr(llm_service,'ask_llm',mock)
    return mock


def test_original_t02_local_pdf_with_stubbed_extraction(monkeypatch,request,tmp_path):
    if not request.config.getoption('--run-docling-pdf'):
        pytest.skip('Enable real local Docling PDF conversion')
    location=os.getenv('STABILIZATION_T02_PDF')
    if not location or not Path(location).is_file():
        pytest.skip('Original T02 is not in the repository; set STABILIZATION_T02_PDF explicitly')
    path=Path(location)
    monkeypatch.setenv('HF_HUB_OFFLINE','1')
    _labelled_stub(monkeypatch,ROWS[1],first_pages={1,2})
    processed=processing_service.process_document(path.read_bytes(),path.name)
    assert len(processed.parsed_document.pages)==5
    result=reconcile_document(processed,repository=repository(),columns=COLUMNS)
    (tmp_path/'parsed_t02.json').write_text(processed.model_dump_json(indent=2),encoding='utf-8')
    assert result.match_status==MatchStatus.EXACT_MATCH, result.model_dump_json(indent=2)
    assert result.matched_record.values['inventory_number']=='L-00022'
    assert not result.review_required and result.counts.unique_differing_fields==0
    assert {f.target_field for f in processed.mapping.mapped_fields}==set(COLUMNS)
    assert {f.page for f in processed.mapping.mapped_fields if f.target_field=='inventory_number'}=={1,2,3,4,5}
    assert not processed.validation_issues
    assert not processed.parsed_document.ocr_pages  # Digital content wasn't forced through full OCR.
    (tmp_path/'t02_result.json').write_text(json.dumps({'pdf_sha256':hashlib.sha256(path.read_bytes()).hexdigest(),
        'scope':'real Docling, manually annotated LLM stub, fixture SQL reads','result':result.model_dump(mode='json')},
        ensure_ascii=False,indent=2),encoding='utf-8')


def test_real_image_only_pdf_local_ocr(monkeypatch,request,tmp_path):
    if not request.config.getoption('--run-docling-pdf'):
        pytest.skip('Enable real local Docling OCR conversion')
    from PIL import Image, ImageDraw, ImageFont
    from reportlab.pdfgen.canvas import Canvas
    from reportlab.lib.utils import ImageReader
    from pypdf import PdfReader
    font_path=Path('C:/Windows/Fonts/arial.ttf')
    if not font_path.exists():
        font_path=Path('/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf')
    font=ImageFont.truetype(str(font_path),30)
    row=dict(ROWS[15]); row['name']='Dell Latitude 5540'
    # A reproducible independent two-page OCR smoke fixture, NOT the absent original T15.
    pdf=io.BytesIO(); canvas=Canvas(pdf,pagesize=(600,800))
    items=list(row.items())
    for part in (items[:6],items[6:]):
        image=Image.new('RGB',(1200,1600),'#eeeeee'); draw=ImageDraw.Draw(image)
        draw.text((90,70),'LOCAL OCR REGRESSION - SYNTHETIC',font=font,fill='#555555')
        for index,(label,value) in enumerate(part):
            draw.text((90,180+index*150),label,font=font,fill='#444444')
            draw.text((670,180+index*150),str(value),font=font,fill='#444444')
        # Mild deterministic skew and low-contrast scan background.
        image=image.rotate(0.6,resample=Image.Resampling.BICUBIC,fillcolor='#eeeeee')
        canvas.drawImage(ImageReader(image),0,0,width=600,height=800)
        canvas.showPage()
    canvas.save(); data=pdf.getvalue()
    assert all(not p.extract_text().strip() for p in PdfReader(io.BytesIO(data)).pages)
    monkeypatch.setenv('HF_HUB_OFFLINE','1')
    parsed=parse_document(data,'independent_ocr_smoke.pdf')
    (tmp_path/'parsed_ocr.json').write_text(parsed.model_dump_json(indent=2),encoding='utf-8')
    assert len(parsed.pages)==2 and parsed.ocr_pages==[1,2]
    assert 'L-00036' in parsed.extraction_text
    assert parsed.source_cells and any(c['from_ocr'] for cells in parsed.source_cells.values() for c in cells)
    # Every field/value still has to exist in real OCR output before a stub
    # can pass it downstream. Unrecognized or low-confidence data require review.
    missing = [name for name,value in row.items() if not any(
        re.search(r'(?<![\w-])'+re.escape(str(value))+r'(?![\w-])', text) for text in parsed.pages.values())]
    # Record recognition gaps explicitly. This is a safety/OCR integration test,
    # not a requirement to manufacture perfect recognition from a noisy image.
    observed = dict(row)
    if 'location' in missing and 'KANDO' in parsed.extraction_text:
        observed['location'] = 'KANDO'  # Actual observed characters, no accent repair.
    monkeypatch.setattr(processing_service,'parse_document',lambda *a,**k:parsed)
    _labelled_stub(monkeypatch,observed)
    processed=processing_service.process_document(data,'independent_ocr_smoke.pdf')
    result=reconcile_document(processed,repository=repository(),columns=COLUMNS)
    assert result.match_status==MatchStatus.EXACT_MATCH
    assert result.counts.unique_differing_fields==0
    assert all(c.status!=ComparisonStatus.DIFFERENT for c in result.field_comparisons)
    if any(f.extraction_uncertain for f in processed.mapping.mapped_fields):
        assert result.review_required
    if missing:
        assert result.review_required
        assert all(a.action_type.value=='MANUAL_REVIEW' for a in result.suggested_actions)
    (tmp_path/'ocr_result.json').write_text(json.dumps({'source':'generated independent image-only fixture',
        'scope':'real local OCR, manual LLM stub, fixture SQL reads','recognition_gaps':missing,
        'result':result.model_dump(mode='json')},
        ensure_ascii=False,indent=2),encoding='utf-8')
