"""Which items pay no GE tax.

The old engine exempted exactly one item — the bond — and taxed the other ~75
exempt items at 2%. That is not a rounding error: it understates the margin on
cooked food, low-level ammo and tools by the full 2% of the sell price, which
is most of the spread on a 200 gp lobster. Those are precisely the items a
capital-constrained free-to-play flipper lives on, so the ranking was biased
against them systematically rather than randomly.

The wiki API publishes no tax-exempt flag, so the list is a hand-maintained
config file (tax_exempt.json) resolved against /mapping by name. Name matching
rather than id matching is deliberate: the wiki's published list names items,
several ids in circulation are wrong or refer to a single charge of a family,
and a renamed item is easier to spot than a silently stale id.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Dict, FrozenSet, Iterable, Optional, Set

CONFIG_PATH = Path(__file__).parent / "tax_exempt.json"

# Item id of a nature rune. High alchemy consumes one per cast, so its live
# price is the cost side of the alchemy floor (§10.1) — read from /latest
# rather than hardcoded, because it drifts with the rune market.
NATURE_RUNE_ID = 561

# Used only when /latest has no nature rune quote. Roughly its long-run level.
NATURE_RUNE_FALLBACK = 100


class ExemptionSet:
    """Resolved tax exemptions for one snapshot of /mapping."""

    __slots__ = ("ids", "unmatched_names")

    def __init__(self, ids: Iterable[int], unmatched_names: Iterable[str] = ()):
        self.ids: FrozenSet[int] = frozenset(ids)
        # Names in the config that no /mapping entry matched. Almost always a
        # typo or a renamed item — surfaced so the config can be corrected
        # instead of quietly under-exempting.
        self.unmatched_names = tuple(sorted(unmatched_names))

    def __contains__(self, item_id: object) -> bool:
        return item_id in self.ids

    def __len__(self) -> int:
        return len(self.ids)


def load_config(path: "str | Path | None" = None) -> dict:
    path = Path(path) if path is not None else CONFIG_PATH
    with open(path, "r") as handle:
        return json.load(handle)


def resolve(items: Optional[Dict[int, object]] = None,
            config: Optional[dict] = None) -> ExemptionSet:
    """Turn the config into the set of exempt item ids.

    items is the /mapping dict (id -> object with a .name). Passing None
    resolves the explicit ids only, which is what a caller without /mapping
    loaded can do.
    """
    if config is None:
        config = load_config()
    ids: Set[int] = set(int(i) for i in config.get("ids", []))
    wanted = {str(n).strip().lower() for n in config.get("names", [])}
    seen: Set[str] = set()
    if items:
        for item_id, item in items.items():
            name = getattr(item, "name", None)
            if not isinstance(name, str):
                continue
            key = name.strip().lower()
            if key in wanted:
                ids.add(int(item_id))
                seen.add(key)
    return ExemptionSet(ids, wanted - seen if items else ())


def nature_rune_cost(quotes: Optional[Dict[int, object]] = None) -> int:
    """Live cost of one high-alchemy cast.

    Takes the instant-buy price: you are the one buying the rune, so you pay
    the ask, not the bid.
    """
    if quotes:
        quote = quotes.get(NATURE_RUNE_ID)
        price = getattr(quote, "high", None) if quote is not None else None
        if isinstance(price, int) and price > 0:
            return price
    return NATURE_RUNE_FALLBACK
