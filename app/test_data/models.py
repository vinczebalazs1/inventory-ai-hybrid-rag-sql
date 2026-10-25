"""The eleven existing business columns; no synthetic device ID column."""
from datetime import date
from pydantic import BaseModel, ConfigDict, Field, field_validator
from .catalog import LOCATIONS

VERSION = "1.0"
REFERENCE_DATE = date(2026, 9, 30)
MINIMUM_DATE = date(2020, 1, 1)


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, frozen=True)


class GenerationConfig(StrictModel):
    seed: int = 42
    count: int = Field(default=1000, ge=1, le=100000)
    locations: tuple[str, ...] = LOCATIONS

    @field_validator("locations")
    @classmethod
    def valid_locations(cls, values):
        if not values or len(set(values)) != len(values) or any(
                not v.strip() or v != v.strip() or len(v) > 80 or "\x00" in v for v in values):
            raise ValueError("Locations must be distinct, nonblank labels of at most 80 characters")
        return values


class InventoryRow(StrictModel):
    item_code: str
    sub_code: int
    activation_date: str
    name: str
    purchase_value: int = Field(ge=0, le=2147483647)
    depreciation: int = Field(ge=0, le=2147483647)
    current_value: int = Field(ge=0, le=2147483647)
    currency: str
    quantity: int
    inventory_number: str
    location: str


COLUMNS = tuple(InventoryRow.model_fields)
INTEGER_COLUMNS = frozenset(("sub_code", "purchase_value", "depreciation", "current_value", "quantity"))
