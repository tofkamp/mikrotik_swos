# mikrotik_swos
Library to access mikrotik SWos API

This library is based on the work of https://github.com/y-martin/pkg-python3-mikrotik-swos
I added support for SWoS switches with more than 32 ports, and used a set() for where there is a selections of ports.

# mikrotik_swos — API Documentation

## Overview

`mikrotik_swos` talks to a MikroTik switch running **SwOS** or **SwOS Lite** over its undocumented `.b` HTTP endpoints (e.g. `/link.b`, `/vlan.b`, `/sys.b`), using HTTP Digest auth. There is no RouterOS-style single client — each "tab" in the SwOS web UI has its own Python class, all inheriting from a shared `Swostab` base.

Requires: `requests`. SwOS is HTTP-only (no HTTPS), so credentials go over plaintext on the LAN — treat management VLANs accordingly.

## Installation

The repo root itself is the `mikrotik_swos` package (it contains `__init__.py`). Clone it so the folder is importable as `mikrotik_swos`:

```bash
git clone https://github.com/tofkamp/mikrotik_swos.git
```

```python
from mikrotik_swos.mikrotik_port import Mikrotik_Port
from mikrotik_swos.mikrotik_vlans import Mikrotik_Vlans
from mikrotik_swos.mikrotik_system import Mikrotik_System
from mikrotik_swos.mikrotik_snmp import Mikrotik_Snmp
from mikrotik_swos.mikrotik_poe import Mikrotik_Poe
from mikrotik_swos.mikrotik_rstp import Mikrotik_Rstp
from mikrotik_swos.mikrotik_lacp import Mikrotik_Lacp
from mikrotik_swos.mikrotik_port_isolation import Mikrotik_Forwarding
```

There is no single "Switch" facade — you instantiate one class per tab you want to touch, and each instantiation makes its own HTTP requests.

## Core concepts

### Connecting

Every class takes the same three constructor args:

```python
sw = Mikrotik_Port("192.168.88.1", "admin", "")
```

- `url` — with or without `http://`; it's added if missing.
- `login`, `password` — SwOS credentials (default `admin` / empty).

On construction, `Swostab.__init__` immediately does two `GET`s (`/link.b`, `/sys.b`) to learn the switch's port/SFP layout and firmware version, then calls the subclass's `_load_tab_data()`, which `GET`s that tab's own page. So **each object creation is a live network round trip** — there's no offline/mock mode.

### Attributes available on every tab object (inherited)

| Attribute | Meaning |
|---|---|
| `.port_count` | Total switch ports |
| `.sfp_count` | Number of SFP ports |
| `.sfp_first_port_id` | 1-based index of the first SFP port |
| `.version` | Firmware version as a float, e.g. `2.17` |

### Reading vs. writing

- Reading is done for you at load time; parsed values live in `self.parsed_data` (or `self._parsed_data` in the vlan/rstp/forwarding modules) or via read-only `@property` accessors (system module).
- Writing follows this pattern in every module:
  1. Call the module's configure/set method one or more times — this only mutates in-memory state.
  2. Call `.save()` to actually `POST` the changes back.

```python
def save(self, dry_run=False)
```
- `dry_run=True` — returns `True`/`False` for "would this write anything" without sending the request.
- `dry_run=False` (default) — POSTs the changed fields and returns `True` on HTTP success, `False` if nothing changed.

Every class also has `.show()`, which just `print()`s a human-readable dump of the tab — useful for debugging, not for programmatic use.

## Class reference

### `Mikrotik_Port` — Link tab (`/link.b`)

```python
port.configure(port_id, **kwargs)
port.save(dry_run=False)
```

| kwarg | Type | Notes |
|---|---|---|
| `name` | str, ≤16 chars | |
| `enabled` | bool | |
| `autoneg` | bool | |
| `duplex` | bool | full duplex |
| `tx_flow_control` / `rx_flow_control` | bool | |
| `speed` | `"10"`/`"100"`/`"1000"`/`"2500"`/`"10000"` | used when `autoneg=False` |
| `sfp_rate` | `"low"`/`"high"` | SFP ports only; firmware ≥ 2.16; raises `ValueError` on a non-SFP port |
| `combo_mode` | `"auto"`/`"copper"`/`"sfp"` | combo ports only; firmware ≥ 2.16; raises `ValueError` on a non-combo port |

```python
port.configure(3, name="uplink", enabled=True, autoneg=False, speed="1000")
port.save()
```

### `Mikrotik_Vlans` — VLAN tab (`/vlan.b`)

```python
vlans.add(vlan_id=..., **kwargs)          # create
vlans.set(vlan_id, **kwargs)              # modify existing
vlans.add_port(vlan_id, port_id)          # add a single member port
vlans.reset_member_cfg()                  # clear membership on all VLANs
vlans.remove(vlan_id)                     # delete a VLAN
vlans.get(vlan_id) / vlans.get_vlans()    # read
vlans.save(dry_run=False)
```

`add`/`set` kwargs: `name` (≤16 chars), `port_isolation`, `learning`, `mirror`, `igmp_snooping` — all bool.

```python
vlans.add(vlan_id=100, name="servers", learning=True)
vlans.add_port(100, 1)
vlans.add_port(100, 5)
vlans.save()
```

### `Mikrotik_System` — System tab + bridge-wide RSTP/IGMP/DHCP (`/sys.b`)

```python
system.set(**kwargs)
system.save(dry_run=False)   # inherited — writes /sys.b
```

Key kwargs: `identity`, `allow_from_net4` (e.g. `"10.0.0.0/8"`), `allow_from_vlan`, `allow_from_port` (list), `watchdog`, `independant_vlan_lookup`, `igmp_snooping`, `igmp_fast_leave` (list), `dhcp_trusted_port` (list), `dhcp_add_information_option`, `rstp_bridge_priority` (hex string, e.g. `"0x8000"`), `rstp_port_cost_mode` (`"short"`/`"long"`), `rsptp_forward_reserved_multicast` (bool — note the kwarg keeps the library's own spelling).

Firmware-gated extras:
- ≥ 2.16: `igmp_querier` (bool, only applied if `igmp_snooping=True`), `igmp_version` (`"v2"`/`"v3"`, default `"v3"`).
- ≥ 2.17: `mikrotik_discovery_protocol` becomes a **port list** (or `True`/`False` to select all/none) instead of a plain bool.

Read-only properties: `.identity`, `.board_name`, `.serial_number`, `.revision`, `.allow_from_port`, `.igmp_fast_leave`, `.dhcp_trusted_port`, `.dhcp_add_information_option`, `.mikrotik_discovery_protocol`.

```python
system.set(identity="sw-core-1", igmp_snooping=True, igmp_querier=True,
           rstp_bridge_priority="0x8000")
system.save()
```

### `Mikrotik_Snmp` — SNMP tab (`/snmp.b`)

```python
snmp.set(enable=True, community="public", contact_info="netops@example.com", location="rack 4")
snmp.save()
```
Read-only from the switch's side: v1/v2c only, no traps, no config writes over SNMP itself.

### `Mikrotik_Poe` — PoE tab (`/poe.b`)

```python
poe.configure_port(port_id=..., **kwargs)
poe.save(dry_run=False)
```

| kwarg | Type |
|---|---|
| `priority` | int 1–8 (1 = highest) |
| `lldp_enabled` | bool — only if `poe.has_lldp` is `True` |
| `poe_output` | `"off"`/`"on"`/`"auto"` |
| `voltage_level` | `"auto"`/`"low"`/`"high"` |

Note `port_id` here is bounded by `poe.port_poe_count` (len of the `poe` array in the payload), not `port_count` — some switches have fewer PoE-capable ports than total ports.

Also exposes live telemetry per port via `_data`: status (`poes`), current (mA), voltage (0.1 V steps), power (0.1 W steps) — see `.show()` for the decode.

### `Mikrotik_Rstp` — RSTP tab, per-port (`/rstp.b`)

```python
rstp.on_port(port_id, rstp_mode)   # rstp_mode: True/False
rstp.save()
```

### `Mikrotik_Lacp` — LACP/LAG tab (`/lacp.b`)

```python
lacp.port_lacp_mode(port_id, mode, group_id=None)
```
`mode`: `"passive"` / `"active"` / `"static"`. `group_id` (0–15) is required/used only for `"static"`. There's no `.save()` override in this file — writes go out via the inherited base `save()`.

```python
lacp.port_lacp_mode(23, "static", group_id=1)
lacp.port_lacp_mode(24, "static", group_id=1)
lacp.save()
```

### `Mikrotik_Forwarding` — Forwarding tab: isolation + per-port VLAN (`/fwd.b`)

```python
fwd.port_isolation(port_id, port_list={})
fwd.port_vlan_config(port_id, mode=None, receive_mode=None,
                      default_vlan_id=None, force_vlan_id=None)
fwd.save()
```

- `port_isolation`: `port_list` is either the string `"any"` (no isolation) or an iterable of port indices this port is allowed to forward to. The port always excludes itself automatically.
- `port_vlan_config`: `mode` ∈ `"disabled"/"optional"/"enabled"/"strict"`; `receive_mode` ∈ `"any"/"only tagged"/"only untagged"`; `default_vlan_id` is an int; `force_vlan_id` is bool. Any argument left `None` is not changed.

```python
fwd.port_isolation(5, port_list={1, 2})       # port 5 can only reach ports 1 and 2
fwd.port_vlan_config(5, mode="strict", default_vlan_id=100)
fwd.save()
```

## Error handling

The library mostly raises plain `ValueError` for out-of-range `port_id`, over-length names, invalid `rstp_bridge_priority`, or SFP/combo-only settings applied to the wrong port type. `KeyError` can surface from unrecognized enum strings (e.g. an unlisted `igmp_version`) since several modules index dicts like `LAG_MODE[mode]` directly instead of using `.get()` with a default. Network/auth failures surface as `requests` exceptions or a non-2xx response from `_get`/`_post` (there's no automatic retry).

## Firmware/version gating summary

| Feature | Minimum firmware |
|---|---|
| `sfp_rate`, `combo_mode` on ports | 2.16 |
| `igmp_querier`, `igmp_version` | 2.16 |
| `mikrotik_discovery_protocol` as a port list (vs. plain bool) | 2.17 |

`sw.version` (float) is populated for you at connect time — check it before setting version-gated fields, since the library itself won't stop you from trying on older firmware (you'll typically get a `KeyError` on the switch's payload instead of a clean error).

## Putting it together with the JSON schema

The schema in the artifact above models a full config file with one section per tab (`system`, `snmp`, `ports[]`, `vlans[]`, `poe[]`, `rstp[]`, `lacp[]`, `forwarding.port_isolation[]`, `forwarding.port_vlan[]`). A loader would look roughly like:

```python
import json
from mikrotik_swos.mikrotik_port import Mikrotik_Port
# ...

cfg = json.load(open("switch.json"))
dev = cfg["device"]

port = Mikrotik_Port(dev["url"], dev["login"], dev.get("password", ""))
for p in cfg.get("ports", []):
    port.configure(p.pop("port_id"), **p)
port.save()
```

repeated per section, instantiating the matching class and calling its configure/set method for each array entry, then `.save()`.

If you'd like, I can also generate a small reference Python script that walks this schema end-to-end and applies a config file to a live switch.
