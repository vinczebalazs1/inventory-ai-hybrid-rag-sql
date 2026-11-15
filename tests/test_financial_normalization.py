"""Hungarian money units must not weaken the shared numeric grammar."""
import pytest

from app.document_processing.models import MappedField, MappingResult
from app.document_processing.validation_service import normalize, number, validate_fields
from app.record_matching.normalization import raw_comparison_value


@pytest.mark.parametrize("field, digits, expected", [
    ("purchase_value", ("326", "000"), 326000),
    ("depreciation", ("171", "306"), 171306),
    ("current_value", ("154", "694"), 154694),
])
@pytest.mark.parametrize("group_space", [" ", "\u00a0", "\u202f"])
@pytest.mark.parametrize("unit_space", [" ", "\u00a0", "\u202f"])
def test_grouped_money_with_ft_retains_raw_evidence(field, digits, expected, group_space, unit_space):
    raw = group_space.join(digits) + unit_space + "Ft"
    evidence = f"{field}: {raw}"
    mapping = MappingResult(mapped_fields=[MappedField(
        source_label=field, target_field=field, raw_value=raw, evidence=evidence, page=1)])
    assert not validate_fields(mapping, [{"column": field, "type": "integer"}])
    result = mapping.mapped_fields[0]
    assert result.normalized_value == expected
    assert result.raw_value == raw and result.evidence == evidence and result.page == 1
    # Reconciliation independently re-normalizes the original value.
    assert raw_comparison_value(raw, "integer", field) == expected


@pytest.mark.parametrize("raw, dtype, expected", [
    ("326000 Ft", "integer", 326000),
    ("326000 HUF", "integer", 326000),
    ("326 000,00 Ft", "integer", 326000),
    ("0 Ft", "integer", 0),
    ("-171\u00a0306\u202fFt", "integer", -171306),
    ("+326 000 ft", "bigint", 326000),
    ("154 694 FT", "integer", 154694),
    ("1 234 567 Ft", "integer", 1234567),
    ("1\u00a0234\u202f567 Ft", "integer", 1234567),
    ("1 234,50 Ft", "numeric", "1234.50"),
    ("-1\u202f234,50 Ft", "decimal", "-1234.50"),
    ("123456789012345678901234567890,12 Ft", "numeric", "123456789012345678901234567890.12"),
])
def test_financial_precision_sign_and_valid_formats(raw, dtype, expected):
    assert normalize(raw, dtype, "purchase_value") == expected


@pytest.mark.parametrize("raw", [
    "32 6000 Ft", "3 26 000 Ft", "326 00 Ft", "326  000 Ft", "326\t000 Ft", "326\n000 Ft",
    "32\u00a06000 Ft", "326\u202f00 Ft", "326.000 Ft", "326,000 Ft", "1.234 Ft", "1,234 Ft",
    "326 000,5 Ft", "NaN Ft", "Infinity Ft", "Ft 326000", "326000Ft", "326000 Ft Ft",
    "326000 Ft extra", "326000 EUR", "326000 - 171306 Ft", "--171306 Ft",
    "- 171306 Ft", "326000\n Ft", "326000\tFt", "Ft",
])
def test_invalid_or_ambiguous_money_stays_invalid(raw):
    mapping = MappingResult(mapped_fields=[MappedField(
        source_label="Purchase value", target_field="purchase_value", raw_value=raw, normalized_value=99)])
    issues = validate_fields(mapping, [{"column": "purchase_value", "type": "integer"}])
    assert len(issues) == 1
    assert mapping.mapped_fields[0].normalized_value is None
    assert mapping.mapped_fields[0].raw_value == raw


@pytest.mark.parametrize("field", ["quantity", "sub_code", "new_numeric_field"])
def test_unit_is_not_accepted_for_other_numeric_fields(field):
    with pytest.raises(ValueError):
        normalize("326 000 Ft", "integer", field)


def test_generic_number_parser_and_text_fields_are_unchanged():
    with pytest.raises(ValueError):
        number("326 000 Ft")
    assert normalize("326 000 Ft", "text", "name") == "326 000 Ft"
    assert normalize("326 000 Ft", "text", "purchase_value") == "326 000 Ft"
