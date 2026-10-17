"""Tests for cart.py.

Money rule for this project: a discount is rounded to the nearest cent,
halves rounding up, and is then subtracted from the subtotal.
"""

import unittest

from cart import apply_discount, cart_total, format_cents, line_total


class LineTests(unittest.TestCase):
    def test_line_total(self):
        self.assertEqual(line_total(3, 250), 750)

    def test_format_cents(self):
        self.assertEqual(format_cents(1234), "12.34")


class DiscountTests(unittest.TestCase):
    def test_zero_discount_is_identity(self):
        self.assertEqual(apply_discount(1000, 0), 1000)

    def test_discount_rounds_half_up(self):
        # 1050 * 5% = 52.5 -> 53 cents off -> 997 left.
        self.assertEqual(apply_discount(1050, 5), 997)

    def test_cart_total_end_to_end(self):
        # subtotal 1050, 5% off -> 997.
        self.assertEqual(cart_total([(2, 499), (1, 52)], 5), 997)


if __name__ == "__main__":
    unittest.main()
