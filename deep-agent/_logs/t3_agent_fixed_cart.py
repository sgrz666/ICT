"""Tiny shopping-cart pricing helper."""

CENTS_PER_UNIT = 100


def line_total(quantity, unit_cents):
    """Total cents for one line item."""
    return quantity * unit_cents


def apply_discount(total_cents, discount_percent):
    """Return total_cents reduced by discount_percent (0-100).

    The discount is rounded to the nearest cent, halves rounding up.
    Adding half a cent before the integer division implements that rule.
    """
    discount_cents = (total_cents * discount_percent + CENTS_PER_UNIT // 2) // CENTS_PER_UNIT
    return total_cents - discount_cents


def cart_total(items, discount_percent=0):
    """Sum a list of (quantity, unit_cents) pairs, then apply a percent discount."""
    subtotal = 0
    for quantity, unit_cents in items:
        subtotal += line_total(quantity, unit_cents)
    return apply_discount(subtotal, discount_percent)


def format_cents(cents):
    """Render cents as a plain '12.34' string."""
    return f"{cents // CENTS_PER_UNIT}.{cents % CENTS_PER_UNIT:02d}"
