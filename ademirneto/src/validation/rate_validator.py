"""
Validation layer: enforces business rules on extracted interchange rates.
Triggers alerts on anomalies and version diffs > 0.5pp.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass

from src.extraction.llm_extractor import InterchangeRule

logger = logging.getLogger(__name__)


@dataclass
class ValidationResult:
    rule: InterchangeRule
    is_valid: bool
    errors: list[str]


RATE_PCT_MAX = 5.0
RATE_PCT_MIN = 0.0
RATE_FIXED_MAX = 2.0
RATE_FIXED_MIN = 0.0


class RateValidator:
    def validate(self, rules: list[InterchangeRule]) -> list[InterchangeRule]:
        valid = []
        for rule in rules:
            result = self._validate_one(rule)
            if result.is_valid:
                valid.append(rule)
            else:
                for err in result.errors:
                    logger.warning("Validation error for '%s': %s", rule.fee_program, err)
        return valid

    def _validate_one(self, rule: InterchangeRule) -> ValidationResult:
        errors: list[str] = []

        if not (RATE_PCT_MIN <= rule.rate_pct <= RATE_PCT_MAX):
            errors.append(f"rate_pct={rule.rate_pct} out of range [{RATE_PCT_MIN}, {RATE_PCT_MAX}]")

        if not (RATE_FIXED_MIN <= rule.rate_fixed_usd <= RATE_FIXED_MAX):
            errors.append(f"rate_fixed_usd={rule.rate_fixed_usd} out of range")

        if rule.cap_usd is not None and rule.cap_usd <= 0:
            errors.append(f"cap_usd={rule.cap_usd} must be positive")

        if rule.floor_usd is not None and rule.floor_usd < 0:
            errors.append(f"floor_usd={rule.floor_usd} must be non-negative")

        if rule.cap_usd and rule.floor_usd and rule.cap_usd < rule.floor_usd:
            errors.append(f"cap_usd < floor_usd: {rule.cap_usd} < {rule.floor_usd}")

        if not rule.fee_program or not rule.fee_program.strip():
            errors.append("fee_program is empty")

        return ValidationResult(rule=rule, is_valid=len(errors) == 0, errors=errors)

    def diff_versions(
        self,
        previous: list[InterchangeRule],
        current: list[InterchangeRule],
        threshold_pp: float = 0.5,
    ) -> list[dict]:
        prev_map = {r.fee_program: r for r in previous}
        alerts = []
        for rule in current:
            prev = prev_map.get(rule.fee_program)
            if prev and abs(rule.rate_pct - prev.rate_pct) > threshold_pp:
                alerts.append({
                    "fee_program": rule.fee_program,
                    "prev_pct": prev.rate_pct,
                    "curr_pct": rule.rate_pct,
                    "delta_pp": rule.rate_pct - prev.rate_pct,
                })
        return alerts
