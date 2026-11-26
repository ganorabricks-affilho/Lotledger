import unittest

import drawer_layout
import money
import paths
from database import DB_PATH, _allocate_cents, drawer_code


class MoneyTests(unittest.TestCase):
    def test_item_prices_keep_three_decimals(self):
        self.assertEqual(money.milli_from_api("0.129"), 129)
        self.assertEqual(money.milli_from_api("1.2"), 1200)
        self.assertEqual(money.milli_from_api("$1,234.567"), 1234567)
        self.assertEqual(money.format_milli(129), "$0.129")
        self.assertEqual(money.format_milli(1234567), "$1,234.567")
        self.assertEqual(money.format_milli_plain(129), "0.129")
        self.assertEqual(money.format_price_string("1.2"), "1.200")
        self.assertEqual(money.milli_from_form("0.129"), 129)
        self.assertEqual(money.dollars_to_milli(0.129), 129)
        with self.assertRaises(ValueError):
            money.milli_from_form("bad")

    def test_cent_fields_stay_whole_cents(self):
        self.assertEqual(money.cents_from_form("$1.20"), 120)
        self.assertEqual(money.cents_from_form(""), 0)
        self.assertEqual(money.cents_from_api("bad"), 0)
        with self.assertRaises(ValueError):
            money.cents_from_form("bad")
        self.assertEqual(money.format_cents(123456), "$1,234.56")
        self.assertEqual(money.format_cents_input(-120), "-1.20")

    def test_milli_to_cents_rounds_the_third_decimal(self):
        self.assertEqual(money.milli_to_cents(169), 17)
        self.assertEqual(money.milli_to_cents(1000), 100)
        self.assertEqual(money.milli_to_cents(0), 0)
        self.assertEqual(money.milli_to_cents(None), 0)

    def test_missing_scale_flag_does_not_multiply(self):
        self.assertFalse(money.line_price_scale_needs_migration(None))
        self.assertFalse(money.line_price_scale_needs_migration("milli"))
        self.assertTrue(money.line_price_scale_needs_migration("cents"))


class AllocateTests(unittest.TestCase):
    def test_shares_add_up(self):
        shares = _allocate_cents(100, [1, 1, 1])
        self.assertEqual(sum(shares), 100)
        self.assertEqual(_allocate_cents(0, [5, 5]), [0, 0])
        self.assertEqual(_allocate_cents(5, [0, 0]), [5, 0])
        self.assertEqual(_allocate_cents(10, []), [])

    def test_thousandths_weights_keep_the_same_cost_split(self):
        cents_weights = [15, 250, 1000]
        milli_weights = [weight * 10 for weight in cents_weights]
        self.assertEqual(_allocate_cents(157903, cents_weights), _allocate_cents(157903, milli_weights))


class PathTests(unittest.TestCase):
    def test_development_database_stays_in_the_project(self):
        expected = paths.project_root() / "data" / "lotledger.db"
        self.assertFalse(paths.is_frozen())
        self.assertEqual(paths.database_path(), expected)
        self.assertEqual(DB_PATH, expected)


class DrawerTests(unittest.TestCase):
    def test_remark_rolls_up_to_the_drawer_code(self):
        self.assertEqual(drawer_code("aj-09-01"), "AJ-09")
        self.assertEqual(drawer_code("D17-01-02"), "D17-01")
        self.assertEqual(drawer_code("not a drawer"), "")

    def test_map_matches_the_cabinets(self):
        self.assertTrue(drawer_layout.on_drawer_map("AA-01"))
        self.assertTrue(drawer_layout.on_drawer_map("AA-14"))
        self.assertFalse(drawer_layout.on_drawer_map("AA-15"))
        self.assertTrue(drawer_layout.on_drawer_map("AI-16"))
        self.assertFalse(drawer_layout.on_drawer_map("AI-17"))
        self.assertTrue(drawer_layout.on_drawer_map("BA-09"))
        self.assertTrue(drawer_layout.on_drawer_map("BA-18"))
        self.assertFalse(drawer_layout.on_drawer_map("BB-09"))
        self.assertTrue(drawer_layout.on_drawer_map("D17-24"))
        self.assertFalse(drawer_layout.on_drawer_map("D17-25"))
        self.assertFalse(drawer_layout.on_drawer_map("AZ-01"))


if __name__ == "__main__":
    unittest.main()
