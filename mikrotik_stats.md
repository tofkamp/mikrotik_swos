Good dataset — this confirms the exact field layout of `/stats.b` and something interesting: your switch's actual payload (firmware 2.18) doesn't include the `rrb`/`trb`/`rrp`/`trp` live-rate fields that `index.html`'s JS unconditionally tries to render (`{n:"Rx Rate",id:"rrb",...}` with no guard). I made the rate fields optional, following the same defensive pattern the library already uses for `has_lldp` in `mikrotik_poe.py`.

Here's `mikrotik_stats.py`, covering the Stats, Errors, and Hist tabs (all backed by the same `/stats.b` endpoint), following the port_id convention we established (1-based for every public method):A few design notes:

- **Follows the `port_id` convention** from the earlier fixes: every public method (`get_stats`, `get_errors`, `get_histogram`, `reset_*`) takes 1-based `port_id`, converted internally with `port_id - 1` for the raw payload arrays.
- **64-bit counters combined for you.** SwOS splits byte/unicast/broadcast/multicast counters into a low word (e.g. `rb`) and high word (`rbh`); `_combine64()` reassembles them into one Python int, mirroring the `I` (high-word) field pattern in `index.html`'s own JS.
- **Reset support included**, not just reads — `reset_counters()`, `reset_errors()`, `reset_histograms()` reproduce SwOS's "Reset Selected …" buttons: select ports (all by default), apply that selection to `/stats.b`, then POST `"*"` to `/resetstats`, `/reseterrs`, or `/resethist` respectively.
- **Defensive about firmware gaps**, same pattern as `has_lldp` in `mikrotik_poe.py`: `has_rates` and `has_tx_queue` are only set `True` when those keys actually appear in the payload, since your own dump shows a real switch (CRS354, 2.18) omitting `rrb`/`trb`/`rrp`/`trp` even though the generic `index.html` UI always tries to render them.

Usage example:
```python
from mikrotik_swos.mikrotik_stats import Mikrotik_Stats

stats = Mikrotik_Stats("192.168.88.1", "admin", "")
print(stats.get_stats(7))       # {'rx_bytes': ..., 'tx_bytes': ..., ...}
print(stats.get_errors(7))
print(stats.get_histogram(7))

stats.reset_counters(port_ids=[7])   # reset just port 7's Stats tab counters
```

One caveat, same as before: I don't have a live switch to test the reset endpoints against, so I'd suggest trying `reset_counters(dry_run=True)` first, and confirming the `/resetstats`-style POST actually behaves as SwOS's JS implies before relying on it in production.
