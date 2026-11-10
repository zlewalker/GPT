"""Shared rounding rules for displayed averages and tier assignment."""
from decimal import Decimal, ROUND_HALF_UP


def rounded_score(score):
    return float(Decimal(str(score)).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP))


def tier_for(score):
    score = rounded_score(score)
    for threshold, tier in [(4.5, 'S'), (4.0, 'A'), (3.0, 'B'), (2.0, 'C')]:
        if score >= threshold:
            return tier
    return 'D'
