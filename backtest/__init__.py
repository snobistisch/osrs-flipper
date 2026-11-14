"""Walk-forward backtest of the flip ranking on real OSRS Wiki price history.

    python3 -m backtest fetch     # download history into data/ (resumable)
    python3 -m backtest build     # raw buckets -> compact panel
    python3 -m backtest run       # walk-forward evaluation, writes a report
    python3 -m backtest smoke     # seconds-long run on the committed fixture

See docs/audit-2026-11.md for the method and its limits. Nothing here places
or automates an in-game order.
"""
