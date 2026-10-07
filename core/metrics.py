"""Funnel, avoidable-rejection and 'what if MatchGuard had been used' metrics. Pure functions."""
from __future__ import annotations

from collections import Counter
from typing import Dict, List, Optional

import pandas as pd

from .filters import violations
from .models import Client, Profile, ShareRecord


def shares_df(shares: List[ShareRecord]) -> pd.DataFrame:
    return pd.DataFrame([s.model_dump() for s in shares])


def funnel(shares: List[ShareRecord]) -> dict:
    df = shares_df(shares)
    by_mm = (df.assign(accepted=df.outcome.eq("accepted"))
               .groupby("matchmaker").agg(shares=("share_id", "count"), accepted=("accepted", "sum")))
    by_mm["acceptance_rate"] = by_mm.accepted / by_mm.shares
    return {
        "shares": len(df),
        "accepted": int(df.outcome.eq("accepted").sum()),
        "rejected": int(df.outcome.eq("rejected").sum()),
        "acceptance_rate": float(df.outcome.eq("accepted").mean()),
        "by_matchmaker": by_mm,
    }


def share_violations(shares: List[ShareRecord], clients: Dict[str, Client], profiles: Dict[str, Profile],
                     learned: Optional[Dict[str, List[str]]] = None) -> Dict[str, list]:
    """share_id -> violations of the client's rules (stated, plus learned if given)."""
    learned = learned or {}
    return {s.share_id: violations(clients[s.client_id], profiles[s.profile_id], learned.get(s.client_id, []))
            for s in shares}


def avoidable_rejections(shares: List[ShareRecord], clients: Dict[str, Client], profiles: Dict[str, Profile]) -> dict:
    """Rejections where the profile broke the client's *stated* preferences when it was shared (data rules, not tags)."""
    v = share_violations(shares, clients, profiles)
    rejected = [s for s in shares if s.outcome == "rejected"]
    avoidable = [s for s in rejected if v[s.share_id]]
    by_rule = Counter(x.rule for s in avoidable for x in {y.rule: y for y in v[s.share_id]}.values())
    return {
        "rejected": len(rejected),
        "avoidable": len(avoidable),
        "rate": len(avoidable) / len(rejected) if rejected else 0.0,
        "by_rule": by_rule,
        "share_ids": [s.share_id for s in avoidable],
    }


def simulate(shares: List[ShareRecord], clients: Dict[str, Client], profiles: Dict[str, Profile],
             learned: Optional[Dict[str, List[str]]] = None) -> dict:
    """Re-run the hard filter over history. Blocked shares would never have been sent."""
    v = share_violations(shares, clients, profiles, learned)
    blocked = [s for s in shares if v[s.share_id]]
    kept = [s for s in shares if not v[s.share_id]]
    blocked_rej = [s for s in blocked if s.outcome == "rejected"]
    blocked_acc = [s for s in blocked if s.outcome == "accepted"]
    kept_acc = sum(1 for s in kept if s.outcome == "accepted")
    base = sum(1 for s in shares if s.outcome == "accepted") / len(shares)
    return {
        "blocked": len(blocked),
        "blocked_rejected": len(blocked_rej),
        "blocked_accepted": len(blocked_acc),  # false positives - would have lost a match the client liked
        "false_positive_details": [(s, v[s.share_id]) for s in blocked_acc],
        "remaining_shares": len(kept),
        "remaining_accepted": kept_acc,
        "baseline_rate": base,
        "projected_rate": kept_acc / len(kept) if kept else 0.0,
        "rejections_avoided_pct": len(blocked_rej) / max(1, sum(1 for s in shares if s.outcome == "rejected")),
    }
