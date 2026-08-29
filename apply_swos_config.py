#!/usr/bin/env python3
"""
apply_swos_config.py

Reference script for tofkamp/mikrotik_swos.

Reads a JSON config file (matching mikrotik_swos.config.schema.json) and
applies it to a live MikroTik SwOS / SwOS Lite switch, tab by tab.

Requires this repo's package on the Python path, e.g.:

    git clone https://github.com/tofkamp/mikrotik_swos.git
    pip install requests
    # optional, for --schema validation:
    pip install jsonschema

Usage:
    python apply_swos_config.py switch.json
    python apply_swos_config.py switch.json --dry-run
    python apply_swos_config.py switch.json --schema mikrotik_swos.config.schema.json -v
"""

import argparse
import json
import logging
import sys

try:
    import jsonschema
    HAVE_JSONSCHEMA = True
except ImportError:
    HAVE_JSONSCHEMA = False

from mikrotik_swos.mikrotik_system import Mikrotik_System
from mikrotik_swos.mikrotik_snmp import Mikrotik_Snmp
from mikrotik_swos.mikrotik_port import Mikrotik_Port
from mikrotik_swos.mikrotik_vlans import Mikrotik_Vlans
from mikrotik_swos.mikrotik_poe import Mikrotik_Poe
from mikrotik_swos.mikrotik_rstp import Mikrotik_Rstp
from mikrotik_swos.mikrotik_lacp import Mikrotik_Lacp
from mikrotik_swos.mikrotik_port_isolation import Mikrotik_Forwarding


log = logging.getLogger("apply_swos_config")


def load_config(path, schema_path=None):
    with open(path, "r", encoding="utf-8") as f:
        cfg = json.load(f)

    if schema_path:
        if not HAVE_JSONSCHEMA:
            log.warning(
                "jsonschema is not installed; skipping validation "
                "(pip install jsonschema)"
            )
        else:
            with open(schema_path, "r", encoding="utf-8") as f:
                schema = json.load(f)
            jsonschema.validate(instance=cfg, schema=schema)
            log.info("config validated against schema")

    if "device" not in cfg or "url" not in cfg["device"]:
        raise ValueError("config must contain a 'device' section with at least 'url'")

    return cfg


def apply_system(dev, section, dry_run):
    if not section:
        return
    log.info("applying system settings")
    sw = Mikrotik_System(dev["url"], dev["login"], dev.get("password", ""))
    sw.set(**section)
    changed = sw.save(dry_run=dry_run)
    log.info("system: %s", "changed" if changed else "no change")


def apply_snmp(dev, section, dry_run):
    if not section:
        return
    log.info("applying snmp settings")
    sw = Mikrotik_Snmp(dev["url"], dev["login"], dev.get("password", ""))
    sw.set(**section)
    changed = sw.save(dry_run=dry_run)
    log.info("snmp: %s", "changed" if changed else "no change")


def apply_ports(dev, entries, dry_run):
    if not entries:
        return
    log.info("applying %d port(s)", len(entries))
    sw = Mikrotik_Port(dev["url"], dev["login"], dev.get("password", ""))
    for entry in entries:
        entry = dict(entry)
        port_id = entry.pop("port_id")
        sw.configure(port_id, **entry)
    changed = sw.save(dry_run=dry_run)
    log.info("ports: %s", "changed" if changed else "no change")


def apply_vlans(dev, entries, dry_run):
    if not entries:
        return
    log.info("applying %d vlan(s)", len(entries))
    sw = Mikrotik_Vlans(dev["url"], dev["login"], dev.get("password", ""))
    existing = set(sw.get_vlans())

    for entry in entries:
        entry = dict(entry)
        vlan_id = entry.pop("vlan_id")
        members = entry.pop("members", None)

        if vlan_id in existing:
            sw.set(vlan_id, **entry)
        else:
            sw.add(vlan_id=vlan_id, **entry)
            existing.add(vlan_id)

        if members is not None:
            # add_port() only adds members, it does not remove ports that
            # are no longer listed. Call vlans.reset_member_cfg() yourself
            # first if you need membership lists to be authoritative.
            for port_id in members:
                sw.add_port(vlan_id, port_id)

    changed = sw.save(dry_run=dry_run)
    log.info("vlans: %s", "changed" if changed else "no change")


def apply_poe(dev, entries, dry_run):
    if not entries:
        return
    log.info("applying poe settings for %d port(s)", len(entries))
    sw = Mikrotik_Poe(dev["url"], dev["login"], dev.get("password", ""))
    for entry in entries:
        # configure_port() reads port_id out of kwargs itself.
        sw.configure_port(**entry)
    changed = sw.save(dry_run=dry_run)
    log.info("poe: %s", "changed" if changed else "no change")


def apply_rstp(dev, entries, dry_run):
    if not entries:
        return
    log.info("applying rstp settings for %d port(s)", len(entries))
    sw = Mikrotik_Rstp(dev["url"], dev["login"], dev.get("password", ""))
    for entry in entries:
        sw.on_port(entry["port_id"], entry["enabled"])
    changed = sw.save(dry_run=dry_run)
    log.info("rstp: %s", "changed" if changed else "no change")


def apply_lacp(dev, entries, dry_run):
    if not entries:
        return
    log.info("applying lacp settings for %d port(s)", len(entries))
    sw = Mikrotik_Lacp(dev["url"], dev["login"], dev.get("password", ""))
    for entry in entries:
        sw.port_lacp_mode(
            entry["port_id"], entry["mode"], group_id=entry.get("group_id")
        )
    # mikrotik_lacp.py has no save() override; this calls the inherited base save().
    changed = sw.save(dry_run=dry_run)
    log.info("lacp: %s", "changed" if changed else "no change")


def apply_forwarding(dev, section, dry_run):
    if not section:
        return
    isolation = section.get("port_isolation") or []
    port_vlan = section.get("port_vlan") or []
    if not isolation and not port_vlan:
        return

    log.info("applying forwarding settings")
    sw = Mikrotik_Forwarding(dev["url"], dev["login"], dev.get("password", ""))

    for entry in isolation:
        allowed = entry["allowed_ports"]
        if allowed != "any":
            allowed = set(allowed)
        sw.port_isolation(entry["port_id"], allowed)

    for entry in port_vlan:
        entry = dict(entry)
        port_id = entry.pop("port_id")
        sw.port_vlan_config(port_id, **entry)

    changed = sw.save(dry_run=dry_run)
    log.info("forwarding: %s", "changed" if changed else "no change")


def main():
    parser = argparse.ArgumentParser(
        description="Apply a JSON config file to a MikroTik SwOS/SwOS Lite switch."
    )
    parser.add_argument("config", help="Path to the config JSON file")
    parser.add_argument(
        "--schema",
        default=None,
        help="Path to mikrotik_swos.config.schema.json to validate the config against",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Compute changes but do not write them to the switch",
    )
    parser.add_argument(
        "-v",
        "--verbose",
        action="store_true",
        help="Enable debug logging (includes raw HTTP request/response bodies)",
    )
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s %(levelname)-7s %(message)s",
    )

    try:
        cfg = load_config(args.config, args.schema)
    except (OSError, json.JSONDecodeError, ValueError) as exc:
        log.error("failed to load config: %s", exc)
        sys.exit(1)
    except jsonschema.ValidationError as exc:  # noqa: F821 - only reachable if jsonschema imported
        log.error("config failed schema validation: %s", exc.message)
        sys.exit(1)

    dev = cfg["device"]

    if args.dry_run:
        log.info("dry-run mode: no changes will be written to %s", dev["url"])

    try:
        apply_system(dev, cfg.get("system"), args.dry_run)
        apply_snmp(dev, cfg.get("snmp"), args.dry_run)
        apply_ports(dev, cfg.get("ports"), args.dry_run)
        apply_vlans(dev, cfg.get("vlans"), args.dry_run)
        apply_poe(dev, cfg.get("poe"), args.dry_run)
        apply_rstp(dev, cfg.get("rstp"), args.dry_run)
        apply_lacp(dev, cfg.get("lacp"), args.dry_run)
        apply_forwarding(dev, cfg.get("forwarding"), args.dry_run)
    except (ValueError, KeyError) as exc:
        log.error("configuration error: %s", exc)
        sys.exit(1)
    except Exception as exc:  # noqa: BLE001 - surface any transport/auth failure to the operator
        log.error("failed to apply config: %s", exc)
        sys.exit(2)

    log.info("done")


if __name__ == "__main__":
    main()
