"""Tests for Money value object and largest-remainder allocation algorithm."""

from decimal import Decimal

import pytest
from hypothesis import given
from hypothesis import strategies as st

from apps.core.money import CurrencyMismatchError, InvalidMoneyError, Money, allocate


def test_money_initialization_and_properties():
    m = Money(1299950, "EGP")
    assert m.amount == 1299950
    assert m.currency == "EGP"
    assert m.to_major() == Decimal("12999.50")
    assert str(m) == "12999.50 EGP"
    assert not m.is_zero()
    assert m.is_positive()
    assert not m.is_negative()


def test_money_from_major():
    m = Money.from_major("12999.50", "EGP")
    assert m.amount == 1299950

    m2 = Money.from_major(Decimal("45.678"), "EGP")  # Round half up -> 45.68 -> 4568
    assert m2.amount == 4568

    # Rejection of floats
    with pytest.raises(TypeError, match="Floats are prohibited"):
        Money.from_major(12.50)  # type: ignore[arg-type]


def test_money_invalid_inputs():
    with pytest.raises(InvalidMoneyError):
        Money("100", "EGP")  # type: ignore[arg-type]

    with pytest.raises(InvalidMoneyError):
        Money(100, "INVALID_CODE")


def test_money_arithmetic():
    m1 = Money(1000, "EGP")
    m2 = Money(550, "EGP")

    assert m1 + m2 == Money(1550, "EGP")
    assert m1 - m2 == Money(450, "EGP")
    assert -m1 == Money(-1000, "EGP")
    assert m1 * 2 == Money(2000, "EGP")
    assert 2 * m1 == Money(2000, "EGP")
    assert m1 * Decimal("1.14") == Money(1140, "EGP")
    assert m1 / 2 == Money(500, "EGP")
    assert m1 / Decimal("3") == Money(333, "EGP")

    # Float multiplication/division rejection
    with pytest.raises(TypeError, match="Floats are prohibited"):
        _ = m1 * 1.5  # type: ignore[operator]
    with pytest.raises(TypeError, match="Floats are prohibited"):
        _ = m1 / 1.5  # type: ignore[operator]


def test_currency_mismatch_raises():
    egp = Money(1000, "EGP")
    usd = Money(1000, "USD")

    with pytest.raises(CurrencyMismatchError):
        _ = egp + usd

    with pytest.raises(CurrencyMismatchError):
        _ = egp - usd

    with pytest.raises(CurrencyMismatchError):
        _ = egp < usd


def test_money_comparisons():
    m1 = Money(1000, "EGP")
    m2 = Money(2000, "EGP")
    m3 = Money(1000, "EGP")

    assert m1 < m2
    assert m1 <= m2
    assert m1 <= m3
    assert m2 > m1
    assert m2 >= m1
    assert m1 == m3


def test_allocate_simple_proportions():
    # 100 piastres divided 1:1:1 -> 34, 33, 33 (exact sum 100)
    total = Money(100, "EGP")
    parts = allocate(total, [1, 1, 1])
    assert [p.amount for p in parts] == [34, 33, 33]
    assert sum(p.amount for p in parts) == 100

    # 100 piastres divided 1:2 -> 33, 67 (exact sum 100)
    parts2 = allocate(total, [1, 2])
    assert [p.amount for p in parts2] == [33, 67]
    assert sum(p.amount for p in parts2) == 100


def test_allocate_zero_total():
    total = Money(0, "EGP")
    parts = allocate(total, [1, 2, 3])
    assert [p.amount for p in parts] == [0, 0, 0]


def test_allocate_empty_or_invalid():
    assert allocate(Money(100, "EGP"), []) == []

    with pytest.raises(ValueError, match="Sum of allocation ratios must be strictly positive"):
        allocate(Money(100, "EGP"), [0, 0])

    with pytest.raises(ValueError, match="Ratios must be non-negative"):
        allocate(Money(100, "EGP"), [1, -1])


@given(
    amount=st.integers(min_value=0, max_value=10_000_000_00),  # up to 10M EGP in piastres
    weights=st.lists(st.integers(min_value=1, max_value=1000), min_size=1, max_size=20),
)
def test_hypothesis_allocation_exact_sum(amount: int, weights: list[int]):
    """Hypothesis invariant test: sum of allocated parts always matches original total exactly."""
    total = Money(amount, "EGP")
    allocated = allocate(total, weights)
    assert len(allocated) == len(weights)
    assert sum(p.amount for p in allocated) == amount
    for p in allocated:
        assert p.amount >= 0
        assert p.currency == "EGP"


def test_money_division_by_zero():
    m = Money(1000, "EGP")
    with pytest.raises(ZeroDivisionError):
        _ = m / 0
    with pytest.raises(ZeroDivisionError):
        _ = m / Decimal("0")


def test_vat_tax_calculation_half_up():
    """Verify Egyptian VAT (14%) calculation on commercial price points."""
    # 125.00 EGP * 0.14 = 17.50 EGP (1750 piastres)
    item_price = Money.from_major("125.00", "EGP")
    vat = item_price * Decimal("0.14")
    assert vat == Money.from_major("17.50", "EGP")
    assert (item_price + vat) == Money.from_major("142.50", "EGP")

    # 99.99 EGP * 0.14 = 13.9986 EGP -> rounded half up to 14.00 EGP (1400 piastres)
    odd_price = Money.from_major("99.99", "EGP")
    vat_odd = odd_price * Decimal("0.14")
    assert vat_odd.amount == 1400
    assert vat_odd == Money.from_major("14.00", "EGP")


def test_multiway_complex_allocation():
    """Verify exact largest-remainder allocation across uneven proportions."""
    total = Money(1000000, "EGP")  # 10,000 EGP
    ratios = [3, 7, 11, 13, 17, 19, 23]
    parts = allocate(total, ratios)
    assert len(parts) == len(ratios)
    assert sum(p.amount for p in parts) == 1000000
