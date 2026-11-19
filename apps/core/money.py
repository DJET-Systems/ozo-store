"""Money value object and allocation utilities for DJET Store.

Invariants:
- All monetary amounts are stored as integer minor units (piastres for EGP: 1 EGP = 100 piastres).
- Floating-point calculations are strictly forbidden to eliminate rounding drift.
- Operations across distinct currencies raise CurrencyMismatchError.
- Remainder distribution uses the largest-remainder method (Hamilton-Hare),
  guaranteeing exact sum preservation down to the single minor unit.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from decimal import ROUND_HALF_UP, Decimal


class CurrencyMismatchError(TypeError):
    """Raised when an operation is attempted between two different currencies."""


class InvalidMoneyError(ValueError):
    """Raised when money amount or currency is structurally invalid."""


@dataclass(frozen=True, slots=True)
class Money:
    """Immutable money value object.

    Attributes:
        amount: Integer minor units (e.g. 100 piastres = 1.00 EGP).
        currency: ISO 4217 uppercase currency code (default "EGP").
    """

    amount: int
    currency: str = "EGP"

    def __post_init__(self) -> None:
        if not isinstance(self.amount, int):
            t_name = type(self.amount).__name__
            raise InvalidMoneyError(
                f"Money amount must be an integer, got {t_name}: {self.amount!r}"
            )
        if not isinstance(self.currency, str) or len(self.currency.strip()) != 3:
            raise InvalidMoneyError(f"Invalid currency code: {self.currency!r}")
        # Enforce canonical uppercase currency code
        object.__setattr__(self, "currency", self.currency.strip().upper())

    @classmethod
    def zero(cls, currency: str = "EGP") -> Money:
        """Return a zero-value Money object in the given currency."""
        return cls(amount=0, currency=currency)

    @classmethod
    def from_major(
        cls,
        value: Decimal | str | int,
        currency: str = "EGP",
        *,
        decimals: int = 2,
    ) -> Money:
        """Construct Money from major units (e.g. 129.50 EGP -> 12950 piastres).

        Uses ROUND_HALF_UP to ensure reliable commercial rounding.
        Floats are intentionally rejected to prevent silent IEEE 754 precision loss.
        """
        if isinstance(value, float):
            raise TypeError("Floats are prohibited for monetary calculations. Pass Decimal or str.")
        dec_val = Decimal(str(value))
        multiplier = Decimal(10**decimals)
        minor_units = int((dec_val * multiplier).quantize(Decimal("1"), rounding=ROUND_HALF_UP))
        return cls(amount=minor_units, currency=currency)

    @classmethod
    def from_minor(cls, amount: int, currency: str = "EGP") -> Money:
        """Construct Money directly from integer minor units."""
        return cls(amount=int(amount), currency=currency)

    def to_major(self, decimals: int = 2) -> Decimal:
        """Convert minor units back to Decimal in major currency units."""
        divisor = Decimal(10**decimals)
        return Decimal(self.amount) / divisor

    def __add__(self, other: object) -> Money:
        if not isinstance(other, Money):
            return NotImplemented
        self._assert_same_currency(other)
        return Money(amount=self.amount + other.amount, currency=self.currency)

    def __sub__(self, other: object) -> Money:
        if not isinstance(other, Money):
            return NotImplemented
        self._assert_same_currency(other)
        return Money(amount=self.amount - other.amount, currency=self.currency)

    def __neg__(self) -> Money:
        return Money(amount=-self.amount, currency=self.currency)

    def __mul__(self, factor: int | Decimal) -> Money:
        if isinstance(factor, float):
            raise TypeError("Floats are prohibited for money multiplication. Use int or Decimal.")
        if isinstance(factor, int):
            return Money(amount=self.amount * factor, currency=self.currency)
        if isinstance(factor, Decimal):
            rounded = int(
                (Decimal(self.amount) * factor).quantize(Decimal("1"), rounding=ROUND_HALF_UP)
            )
            return Money(amount=rounded, currency=self.currency)
        return NotImplemented

    __rmul__ = __mul__

    def __truediv__(self, divisor: int | Decimal) -> Money:
        if isinstance(divisor, float):
            raise TypeError("Floats are prohibited for money division. Use int or Decimal.")
        if divisor == 0:
            raise ZeroDivisionError("Cannot divide Money by zero.")
        dec_div = Decimal(str(divisor))
        rounded = int(
            (Decimal(self.amount) / dec_div).quantize(Decimal("1"), rounding=ROUND_HALF_UP)
        )
        return Money(amount=rounded, currency=self.currency)

    def __lt__(self, other: object) -> bool:
        if not isinstance(other, Money):
            return NotImplemented
        self._assert_same_currency(other)
        return self.amount < other.amount

    def __le__(self, other: object) -> bool:
        if not isinstance(other, Money):
            return NotImplemented
        self._assert_same_currency(other)
        return self.amount <= other.amount

    def __gt__(self, other: object) -> bool:
        if not isinstance(other, Money):
            return NotImplemented
        self._assert_same_currency(other)
        return self.amount > other.amount

    def __ge__(self, other: object) -> bool:
        if not isinstance(other, Money):
            return NotImplemented
        self._assert_same_currency(other)
        return self.amount >= other.amount

    def _assert_same_currency(self, other: Money) -> None:
        if self.currency != other.currency:
            raise CurrencyMismatchError(
                f"Currency mismatch: cannot operate between {self.currency} and {other.currency}"
            )

    def is_zero(self) -> bool:
        return self.amount == 0

    def is_positive(self) -> bool:
        return self.amount > 0

    def is_negative(self) -> bool:
        return self.amount < 0

    @property
    def formatted(self) -> str:
        """Formatted representation, e.g. '129.50 EGP'."""
        return str(self)

    def __str__(self) -> str:
        major = self.to_major()
        return f"{major:.2f} {self.currency}"

    def __repr__(self) -> str:
        return f"Money(amount={self.amount}, currency={self.currency!r})"


def allocate(total: Money, ratios: Sequence[int | Decimal]) -> list[Money]:
    """Distribute total amount across given ratios using largest-remainder method.

    Guarantees:
    - sum(allocated) == total.amount exactly (no penny/piastre lost or invented).
    - Stable, deterministic distribution of rounding remainders.
    - Preserves sign when distributing.
    """
    if not ratios:
        return []

    for r in ratios:
        if isinstance(r, float):
            raise TypeError("Floats are prohibited in allocate ratios. Use int or Decimal.")
        if r < 0:
            raise ValueError(f"Ratios must be non-negative, got {r}")

    dec_ratios = [Decimal(str(r)) for r in ratios]
    total_ratio = sum(dec_ratios)

    if total_ratio == Decimal("0"):
        raise ValueError("Sum of allocation ratios must be strictly positive.")

    total_amount = total.amount
    # Exact shares: (total_amount * ratio) / total_ratio
    exact_shares = [(Decimal(total_amount) * r) / total_ratio for r in dec_ratios]
    base_shares = [int(s.to_integral_value(rounding="ROUND_FLOOR")) for s in exact_shares]

    remainder = total_amount - sum(base_shares)

    # Sort remaining fractions in descending order to assign remainder units
    fractions = [(exact_shares[i] - Decimal(base_shares[i]), i) for i in range(len(ratios))]
    # Sort primarily by fraction descending, secondarily by index ascending (deterministic)
    fractions.sort(key=lambda item: (-item[0], item[1]))

    allocated = list(base_shares)
    for i in range(remainder):
        idx = fractions[i][1]
        allocated[idx] += 1

    if sum(allocated) != total_amount:
        raise InvalidMoneyError(f"Allocation invariant broken: sum({allocated}) != {total_amount}")

    return [Money(amount=a, currency=total.currency) for a in allocated]
