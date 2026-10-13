"""Validated, explicit reconciliation policy; thresholds are not probabilities."""
import os
import re
from typing import Literal

from dotenv import load_dotenv
from pydantic import ConfigDict, Field, model_validator

from .models import Contract

IDENTIFIER_FIELDS = ("inventory_number", "item_code")
SENSITIVE_FIELDS = frozenset((*IDENTIFIER_FIELDS, "sub_code", "purchase_value", "depreciation", "current_value", "currency"))


class MatchingSettings(Contract):
    model_config = ConfigDict(extra="forbid", strict=True, frozen=True, allow_inf_nan=False)
    target_schema: str = "public"
    target_table: str = "inventory_items"
    strategy: Literal["exact_only", "hybrid"] = "hybrid"
    max_candidates: int = Field(default=100, ge=1, le=10000)
    max_scan_rows: int = Field(default=1000, ge=1, le=100000)
    query_timeout_ms: int = Field(default=3000, ge=1, le=60000)
    connect_timeout_seconds: int = Field(default=5, ge=1, le=60)
    max_field_length: int = Field(default=1000, ge=1, le=10000)
    exact_threshold: float = Field(default=0.95, ge=0, le=1)
    likely_threshold: float = Field(default=0.72, ge=0, le=1)
    ambiguity_margin: float = Field(default=0.05, ge=0, le=1)
    duplicate_threshold: float = Field(default=0.45, ge=0, le=1)
    model_conflict_cap: float = Field(default=0.4, ge=0, le=1)
    inventory_number_weight: float = Field(default=0.5, gt=0, le=100)
    item_code_weight: float = Field(default=0.4, gt=0, le=100)
    sub_code_weight: float = Field(default=0.1, gt=0, le=100)
    name_weight: float = Field(default=0.3, gt=0, le=100)
    location_weight: float = Field(default=0.1, gt=0, le=100)
    activation_date_weight: float = Field(default=0.1, gt=0, le=100)

    @model_validator(mode="after")
    def coherent(self) -> "MatchingSettings":
        if not 0 < self.duplicate_threshold < self.likely_threshold < self.exact_threshold <= 1:
            raise ValueError("Require 0 < duplicate < likely < exact <= 1")
        if self.model_conflict_cap >= self.likely_threshold:
            raise ValueError("Model conflict cap must be below likely threshold")
        if self.max_scan_rows < self.max_candidates:
            raise ValueError("max_scan_rows must be >= max_candidates")
        if self.ambiguity_margin >= self.likely_threshold:
            raise ValueError("Ambiguity margin must be smaller than likely threshold")
        for name in (self.target_schema, self.target_table):
            if not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", name):
                raise ValueError("Invalid configured SQL identifier")
        return self

    @property
    def weights(self) -> dict[str, float]:
        return {name: getattr(self, f"{name}_weight") for name in
                (*IDENTIFIER_FIELDS, "sub_code", "name", "location", "activation_date")}

    @classmethod
    def from_env(cls) -> "MatchingSettings":
        load_dotenv()
        values = {}
        for name, field in cls.model_fields.items():
            raw = os.getenv(f"MATCHING_{name.upper()}")
            if raw is not None:
                values[name] = int(raw) if field.annotation is int else float(raw) if field.annotation is float else raw
        return cls(**values)
