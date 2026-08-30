#!/usr/bin/env python3
from mikrotik_swos import utils
from mikrotik_swos.swostab import Swostab

# payload (from /stats.b) — Stats + Errors + Hist tabs share this one page.
# {rb:[...],rbh:[...],tb:[...],tbh:[...],rtp:[...],ttp:[...],
#  rup:[...],ruph:[...],tup:[...],tuph:[...],
#  rbp:[...],rbph:[...],tbp:[...],tbph:[...],
#  rmp:[...],rmph:[...],tmp:[...],tmph:[...],
#  tq:[...],tqb:[...],resc:[0x0,0x0],
#  rpp:[...],rte:[...],rfcs:[...],rae:[...],rr:[...],fr:[...],rov:[...],
#  tpp:[...],tur:[...],tcl:[...],tmc:[...],tec:[...],tlc:[...],tdf:[...],rese:[0x0,0x0],
#  p64:[...],p65:[...],p128:[...],p256:[...],p512:[...],p1k:[...],resh:[0x0,0x0]}
#
# rrb/trb (Rx/Tx Rate) and rrp/trp (Rx/Tx Packet Rate) are rendered by SwOS's
# own web UI, but are not present on every firmware/hardware combination
# (e.g. absent on a CRS354-48P-4S+2Q+ on 2.18) — see has_rates below.

PAGE = "/stats.b"

# SwOS's own web UI divides the raw counter by these factors before display.
RATE_SCALE = {
    "rx_rate": 0.01,
    "tx_rate": 0.01,
    "rx_packet_rate": 1.28,
    "tx_packet_rate": 1.28,
}

RESET_ENDPOINTS = {
    "reset_counters": ("/resetstats", "resc"),
    "reset_errors": ("/reseterrs", "rese"),
    "reset_histograms": ("/resethist", "resh"),
}


def _combine64(low_list, high_list, i):
    """
    Combine a pair of 32-bit hex words (low, high) for port index i (0-based,
    matching the raw payload lists) into a single 64-bit int. high_list may
    be None if the switch doesn't report a high word for that counter.
    """
    low = int(low_list[i], 16)
    high = int(high_list[i], 16) if high_list is not None else 0
    return low + (high << 32)


class Mikrotik_Stats(Swostab):
    def _load_tab_data(self):
        self._page = PAGE
        self._data = utils.mikrotik_to_json(self._get(PAGE).text)

        # Not every firmware/hardware combination reports live rates.
        self.has_rates = "rrb" in self._data
        # Tx Queue is present in the payload but disabled in SwOS's own UI
        # (Z(!1, ...)); keep it opt-in the same way.
        self.has_tx_queue = "tq" in self._data

        self.parsed_data = {
            "reset_counters": utils.decode_listofflags(self._data["resc"], self.port_count),
            "reset_errors": utils.decode_listofflags(self._data["rese"], self.port_count),
            "reset_histograms": utils.decode_listofflags(self._data["resh"], self.port_count),
        }

    def _check_port(self, port_id):
        if port_id < 1 or port_id > self.port_count:
            raise ValueError(f"port_id is outside 1..{self.port_count}")

    def get_stats(self, port_id):
        """
        Returns a dict with the counters shown on the "Stats" tab for port_id
        (1-based). Byte/packet totals (rx_bytes, tx_bytes, *_unicasts,
        *_broadcasts, *_multicasts) are combined into full 64-bit ints from
        their low/high hex words. rx_rate/tx_rate/rx_packet_rate/tx_packet_rate
        are only present when self.has_rates is True.
        """
        self._check_port(port_id)
        i = port_id - 1
        d = self._data

        stats = {
            "rx_bytes": _combine64(d["rb"], d.get("rbh"), i),
            "tx_bytes": _combine64(d["tb"], d.get("tbh"), i),
            "rx_total_packets": int(d["rtp"][i], 16),
            "tx_total_packets": int(d["ttp"][i], 16),
            "rx_unicasts": _combine64(d["rup"], d.get("ruph"), i),
            "tx_unicasts": _combine64(d["tup"], d.get("tuph"), i),
            "rx_broadcasts": _combine64(d["rbp"], d.get("rbph"), i),
            "tx_broadcasts": _combine64(d["tbp"], d.get("tbph"), i),
            "rx_multicasts": _combine64(d["rmp"], d.get("rmph"), i),
            "tx_multicasts": _combine64(d["tmp"], d.get("tmph"), i),
        }

        if self.has_rates:
            stats["rx_rate"] = int(d["rrb"][i], 16) / RATE_SCALE["rx_rate"]
            stats["tx_rate"] = int(d["trb"][i], 16) / RATE_SCALE["tx_rate"]
            stats["rx_packet_rate"] = int(d["rrp"][i], 16) / RATE_SCALE["rx_packet_rate"]
            stats["tx_packet_rate"] = int(d["trp"][i], 16) / RATE_SCALE["tx_packet_rate"]

        if self.has_tx_queue:
            stats["tx_queue_packets"] = int(d["tq"][i], 16)
            stats["tx_queue_kb"] = int(d["tqb"][i], 16)

        return stats

    def get_errors(self, port_id):
        """
        Returns a dict with the counters shown on the "Errors" tab for
        port_id (1-based).
        """
        self._check_port(port_id)
        i = port_id - 1
        d = self._data
        return {
            "rx_pauses": int(d["rpp"][i], 16),
            "rx_mac_errors": int(d["rte"][i], 16),
            "rx_fcs_errors": int(d["rfcs"][i], 16),
            "rx_jabber": int(d["rae"][i], 16),
            "rx_runts": int(d["rr"][i], 16),
            "rx_fragments": int(d["fr"][i], 16),
            "rx_overruns": int(d["rov"][i], 16),
            "tx_pauses": int(d["tpp"][i], 16),
            "tx_underruns": int(d["tur"][i], 16),
            "tx_collisions": int(d["tcl"][i], 16),
            "tx_multiple_collisions": int(d["tmc"][i], 16),
            "tx_excessive_collisions": int(d["tec"][i], 16),
            "tx_late_collisions": int(d["tlc"][i], 16),
            "tx_deferred": int(d["tdf"][i], 16),
        }

    def get_histogram(self, port_id):
        """
        Returns a dict with the packet-size histogram buckets (packet counts
        by frame size, in bytes) shown on the "Hist" tab for port_id (1-based).
        """
        self._check_port(port_id)
        i = port_id - 1
        d = self._data
        return {
            "64": int(d["p64"][i], 16),
            "65-127": int(d["p65"][i], 16),
            "128-255": int(d["p128"][i], 16),
            "256-511": int(d["p256"][i], 16),
            "512-1023": int(d["p512"][i], 16),
            "1024-max": int(d["p1k"][i], 16),
        }

    def get_all_stats(self):
        """List of get_stats() dicts for every port, 1-based order (port 1 first)."""
        return [self.get_stats(i) for i in range(1, self.port_count + 1)]

    def get_all_errors(self):
        """List of get_errors() dicts for every port, 1-based order."""
        return [self.get_errors(i) for i in range(1, self.port_count + 1)]

    def get_all_histograms(self):
        """List of get_histogram() dicts for every port, 1-based order."""
        return [self.get_histogram(i) for i in range(1, self.port_count + 1)]

    def _reset(self, parsed_key, port_ids, dry_run):
        page, data_key = RESET_ENDPOINTS[parsed_key]

        ports = set(range(1, self.port_count + 1)) if port_ids is None else set(port_ids)
        for port_id in ports:
            self._check_port(port_id)

        self.parsed_data[parsed_key] = ports
        self._update_data(data_key, utils.encode_listofflags(ports, self.port_count))

        if dry_run:
            return self._data_changed
        if not self._save(dry_run=False):
            return False
        # Mirrors the SwOS web UI: apply the port selection first (above),
        # then trigger the actual reset with a bare POST to the reset endpoint.
        return self._post(page, "*").ok

    def reset_counters(self, port_ids=None, dry_run=False):
        """
        Reset the Stats tab counters ("Reset Selected Counters" button).
        port_ids: iterable of 1-based port indexes to reset, or None (default)
        to reset every port.
        """
        return self._reset("reset_counters", port_ids, dry_run)

    def reset_errors(self, port_ids=None, dry_run=False):
        """
        Reset the Errors tab counters ("Reset Selected Errors" button).
        port_ids: iterable of 1-based port indexes to reset, or None (default)
        to reset every port.
        """
        return self._reset("reset_errors", port_ids, dry_run)

    def reset_histograms(self, port_ids=None, dry_run=False):
        """
        Reset the Hist tab counters ("Reset Selected Histograms" button).
        port_ids: iterable of 1-based port indexes to reset, or None (default)
        to reset every port.
        """
        return self._reset("reset_histograms", port_ids, dry_run)

    def show(self):
        print("stats tab")
        for i in range(1, self.port_count + 1):
            s = self.get_stats(i)
            print(f"* port {i}")
            if self.has_rates:
                print(f"    rx rate: {s['rx_rate']} B/s   tx rate: {s['tx_rate']} B/s")
                print(f"    rx packet rate: {s['rx_packet_rate']}/s   tx packet rate: {s['tx_packet_rate']}/s")
            print(f"    rx bytes: {s['rx_bytes']}   tx bytes: {s['tx_bytes']}")
            print(f"    rx total packets: {s['rx_total_packets']}   tx total packets: {s['tx_total_packets']}")
            print(f"    rx unicasts: {s['rx_unicasts']}   tx unicasts: {s['tx_unicasts']}")
            print(f"    rx broadcasts: {s['rx_broadcasts']}   tx broadcasts: {s['tx_broadcasts']}")
            print(f"    rx multicasts: {s['rx_multicasts']}   tx multicasts: {s['tx_multicasts']}")
        print("")

        print("errors tab")
        for i in range(1, self.port_count + 1):
            e = self.get_errors(i)
            print(f"* port {i}")
            print(f"    rx pauses: {e['rx_pauses']}   tx pauses: {e['tx_pauses']}")
            print(f"    rx mac errors: {e['rx_mac_errors']}   rx fcs errors: {e['rx_fcs_errors']}")
            print(f"    rx jabber: {e['rx_jabber']}   rx runts: {e['rx_runts']}   rx fragments: {e['rx_fragments']}")
            print(f"    rx overruns: {e['rx_overruns']}   tx underruns: {e['tx_underruns']}")
            print(
                f"    tx collisions: {e['tx_collisions']}"
                f" (multiple: {e['tx_multiple_collisions']},"
                f" excessive: {e['tx_excessive_collisions']},"
                f" late: {e['tx_late_collisions']})"
            )
            print(f"    tx deferred: {e['tx_deferred']}")
        print("")

        print("hist tab")
        for i in range(1, self.port_count + 1):
            h = self.get_histogram(i)
            print(f"* port {i}")
            print(f"    64: {h['64']}   65-127: {h['65-127']}   128-255: {h['128-255']}")
            print(f"    256-511: {h['256-511']}   512-1023: {h['512-1023']}   1024-max: {h['1024-max']}")
        print("")
