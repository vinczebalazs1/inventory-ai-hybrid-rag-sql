"""Pure deterministic generation; independent of DB, Docling, LLM and Qdrant."""
from datetime import date, timedelta
from random import Random
from .catalog import CATALOG, DISTRIBUTION
from .models import GenerationConfig, InventoryRow, REFERENCE_DATE


def allocation(count: int) -> dict[str, int]:
    """Largest remainder allocation with a fixed category order for ties."""
    allocated = {category: count * weight // 1000 for category, weight in DISTRIBUTION.items()}
    remainder_order = sorted(DISTRIBUTION, key=lambda k: -(count * DISTRIBUTION[k] % 1000))
    for category in remainder_order[:count - sum(allocated.values())]:
        allocated[category] += 1
    return allocated


def generate(config: GenerationConfig | None = None) -> list[InventoryRow]:
    config = config or GenerationConfig()
    rng = Random(config.seed)
    rows = []
    for category, count in allocation(config.count).items():
        products = [product for product in CATALOG if product.category == category]
        for index in range(count):
            product = products[index % len(products)]
            first = date.fromisoformat(product.eligible_from)
            activation = first + timedelta(days=rng.randrange((REFERENCE_DATE - first).days + 1))
            purchase = rng.randrange(product.minimum_price // 1000, product.maximum_price // 1000 + 1) * 1000
            age = (REFERENCE_DATE - activation).days
            depreciation = purchase * min(age, product.useful_life_days) // product.useful_life_days
            rows.append(InventoryRow(item_code=product.item_code, sub_code=0,
                activation_date=activation.isoformat(), name=product.name, purchase_value=purchase,
                depreciation=depreciation, current_value=purchase - depreciation, currency="HUF",
                quantity=1, inventory_number=f"L-{len(rows) + 1:05d}",
                location=config.locations[rng.randrange(len(config.locations))]))
    return rows
