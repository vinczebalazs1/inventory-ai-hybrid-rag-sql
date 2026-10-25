"""Dataset quality checks, independent of matching outputs."""
from collections import Counter
from datetime import date
from .catalog import BY_CODE
from .generator import allocation
from .models import GenerationConfig, InventoryRow, MINIMUM_DATE, REFERENCE_DATE


def validate_rows(rows: list[InventoryRow], config: GenerationConfig) -> dict:
    issues = Counter()
    categories, models, locations, codes = Counter(), Counter(), Counter(), Counter()
    identifiers = [row.inventory_number for row in rows]
    issues["record_count"] = int(len(rows) != config.count)
    issues["duplicate_inventory_numbers"] = len(identifiers) - len(set(identifiers))
    for row in rows:
        issues["invalid_inventory_numbers"] += int(not row.inventory_number.strip())
        issues["invalid_quantities"] += int(row.quantity != 1)
        issues["invalid_names"] += int(not row.name.strip())
        issues["invalid_locations"] += int(row.location not in config.locations)
        issues["invalid_currencies"] += int(row.currency != "HUF")
        issues["financial_relationship"] += int(row.current_value != row.purchase_value - row.depreciation)
        product = BY_CODE.get(row.item_code)
        issues["catalog_mismatch"] += int(product is None or row.name != product.name or row.sub_code != 0)
        models[row.name] += 1
        locations[row.location] += 1
        codes[row.item_code] += 1
        if product:
            categories[product.category] += 1
            issues["price_band"] += int(not product.minimum_price <= row.purchase_value <= product.maximum_price
                                       or row.purchase_value % 1000 != 0)
        try:
            activation = date.fromisoformat(row.activation_date)
            issues["invalid_dates"] += int(activation.isoformat() != row.activation_date or
                not MINIMUM_DATE <= activation <= REFERENCE_DATE or
                (product is not None and activation < date.fromisoformat(product.eligible_from)))
            if product:
                expected = row.purchase_value * min(max((REFERENCE_DATE - activation).days, 0), product.useful_life_days) // product.useful_life_days
                issues["depreciation_rule"] += int(row.depreciation != expected)
        except ValueError:
            issues["invalid_dates"] += 1
    expected_ids = {f"L-{n:05d}" for n in range(1, config.count + 1)}
    issues["canonical_identifiers"] = int(set(identifiers) != expected_ids)
    issues["category_distribution"] = int(dict(categories) != {k: v for k, v in allocation(config.count).items() if v})
    return {"validation_passed": not any(issues.values()), "record_count": len(rows),
            "unique_inventory_numbers": len(set(identifiers)), "violations": dict(issues),
            "category_counts": dict(categories), "model_counts": dict(models),
            "location_counts": dict(locations), "repeated_item_codes": sum(v > 1 for v in codes.values())}


def require_valid(rows: list[InventoryRow], config: GenerationConfig) -> dict:
    report = validate_rows(rows, config)
    if not report["validation_passed"]:
        raise ValueError("Invalid dataset: " + ", ".join(k for k, v in report["violations"].items() if v))
    return report
