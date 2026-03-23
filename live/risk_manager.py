"""
Risk Manager — Guardrails that protect your capital.

Rules:
1. Kill switch: stop all trading if drawdown exceeds threshold
2. Position limits: never put too much in one stock
3. Trade validation: sanity-check every order before submission
"""

import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import logging
from dataclasses import dataclass

from config import MAX_DRAWDOWN_PCT, MAX_POSITION_PCT

logger = logging.getLogger("risk_manager")


@dataclass
class RiskCheck:
    passed: bool
    reason: str = ""


class RiskManager:
    def __init__(
        self,
        max_drawdown_pct: float = MAX_DRAWDOWN_PCT,
        max_position_pct: float = MAX_POSITION_PCT,
    ):
        self.max_drawdown_pct = max_drawdown_pct
        self.max_position_pct = max_position_pct
        self.peak_equity = 0.0
        self.killed = False
        self.kill_reason = ""

    def update_equity(self, current_equity: float) -> RiskCheck:
        """Track equity and trigger kill switch if drawdown exceeds limit."""
        if current_equity > self.peak_equity:
            self.peak_equity = current_equity

        if self.peak_equity > 0:
            drawdown = (current_equity - self.peak_equity) / self.peak_equity
            if drawdown < -self.max_drawdown_pct:
                self.killed = True
                self.kill_reason = (
                    f"KILL SWITCH: Drawdown {drawdown:.1%} exceeds limit "
                    f"{-self.max_drawdown_pct:.1%}. Peak=${self.peak_equity:,.2f}, "
                    f"Current=${current_equity:,.2f}"
                )
                logger.critical(self.kill_reason)
                return RiskCheck(passed=False, reason=self.kill_reason)

        return RiskCheck(passed=True)

    def check_trade(
        self,
        symbol: str,
        trade_value: float,
        portfolio_value: float,
    ) -> RiskCheck:
        """Validate a single trade before execution."""
        if self.killed:
            return RiskCheck(passed=False, reason=f"Trading killed: {self.kill_reason}")

        # Position size check
        position_pct = abs(trade_value) / portfolio_value if portfolio_value > 0 else 1.0
        if position_pct > self.max_position_pct:
            reason = (
                f"Position too large: {symbol} would be {position_pct:.1%} of portfolio "
                f"(limit: {self.max_position_pct:.1%})"
            )
            logger.warning(reason)
            return RiskCheck(passed=False, reason=reason)

        # Sanity check: no negative values
        if portfolio_value <= 0:
            return RiskCheck(passed=False, reason="Portfolio value is zero or negative")

        return RiskCheck(passed=True)

    def check_weights(
        self,
        target_weights: dict[str, float],
        portfolio_value: float,
    ) -> dict[str, float]:
        """Validate and cap target weights. Returns adjusted weights."""
        adjusted = {}
        for symbol, weight in target_weights.items():
            if weight <= 0:
                continue

            # Cap at max position size
            capped_weight = min(weight, self.max_position_pct)
            if capped_weight != weight:
                logger.info(f"Capped {symbol} weight from {weight:.1%} to {capped_weight:.1%}")

            adjusted[symbol] = capped_weight

        # Ensure total doesn't exceed 100%
        total = sum(adjusted.values())
        if total > 1.0:
            scale = 1.0 / total
            adjusted = {s: w * scale for s, w in adjusted.items()}
            logger.info(f"Scaled weights down by {scale:.2f} to stay within 100%")

        return adjusted

    @property
    def status(self) -> str:
        if self.killed:
            return f"KILLED: {self.kill_reason}"
        if self.peak_equity > 0:
            return f"Active | Peak: ${self.peak_equity:,.2f} | Kill at: ${self.peak_equity * (1 - self.max_drawdown_pct):,.2f}"
        return "Active | Awaiting first equity update"
