#!/usr/bin/env python3


import json
import re
import socket
import struct


def mikrotik_to_json(broken_json):
    result = re.sub(r'([{,])([a-zA-Z][a-zA-Z0-9]+)', '\\1"\\2"', broken_json)
    result = re.sub(r'\'', '"', result)
    result = re.sub(r'(0x[0-9a-zA-Z]+)', '"\\1"', result)
    return json.loads(result)

def json_to_mikrotik(data):
    result = re.sub(r'"(0x[0-9a-zA-Z]+)"', '\\1', json.dumps(data))
    result = re.sub(r'"([a-zA-Z][a-zA-Z0-9]+)":', '\\1:', result)
    result = re.sub(r'"', '\'', result)
    return result.replace(" ", "")

# 53465031 -> SFP1
def decode_string(s):
    return bytes.fromhex(s).decode("ascii")

# SFP1 -> 53465031
def encode_string(s):
    if isinstance(s, str):
        return s.encode("ascii").hex()

    return None

# 0x1c20005 -> [1, 0, 1, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1, 1, 1, 0]
def decode_listofflags_old(s, zfill=0):
    flags = []

    if s is None or len(s) == 0:
        return flags
    #print(type(s),s)
    # list is reversed (example port1 is last item)
    flags_str = bin(int(s, 16))[2:]
    if zfill > 0:
        flags_str = flags_str.zfill(zfill)

    flags_list = list(flags_str)
    i = len(flags_list)
    while i:
        flags.append(int(flags_list[i-1]))
        i -= 1
    return flags

def decode_listofflags(s, zfill=0):
    def _decode2(s, start_port_nr = 1):
        flags = set()
        flags_int = int(s,16)
        bit_mask = 1
        port_nr = start_port_nr
        while bit_mask <= flags_int:
            if flags_int & bit_mask:
                flags.add(port_nr)
            bit_mask <<= 1
            port_nr += 1
        return flags

    if s is None or len(s) == 0:
        return flags

    if type(s) is list:
        # it is from a switch with more than 32 ports
        flags = _decode2(s[0], start_port_nr = 33) | _decode2(s[1], start_port_nr = 1)
    else:
        # the switch has less than 32 ports
        flags = _decode2(s , start_port_nr = 1)
    return flags

# [1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0] --> 0x01ffff
def encode_listofflags_old(flags):
    if not isinstance(flags, list):
        return None

    # list need to be reversed
    if len(flags) > 0:
        flags_str = "".join(map(str, flags))[::-1]
    else:
        flags_str = "0"

    value = hex(int(flags_str, 2))
    if len(value) % 2:
        value = value.replace("0x", "0x0")

    return value

def encode_listofflags(flags, nr_of_ports):
    def _encode2(flags, start_port_nr = 1, end_port_nr = 32):
        if not isinstance(flags, set):
            return None
        value = 0
        bit_mask = 1
        for port_nr in range(start_port_nr, end_port_nr + 1):
            if port_nr in flags:
                value |= bit_mask
            bit_mask <<= 1
        return hex(value)

    if not isinstance(flags, set):
        return None
    if nr_of_ports > 32:
        value = [ _encode2(flags,start_port_nr = 33, end_port_nr = 64),  _encode2(flags,start_port_nr = 1, end_port_nr = 32) ]
    else:
        value = _encode2(flags,start_port_nr = 1, end_port_nr = nr_of_ports)
    return value
    
# with pad=8 => 0xc26005 becomes 0x00c26005
def hex_str_with_pad(s, pad=0):
    if s is None:
        return None

    if isinstance(s, str):
        s = int(s, 16)

    if pad == 0 or pad is None:
        return hex(s)
    else:
        return '0x{0:0{1}x}'.format(s,pad)

# 10.31.0.250 => 0xfa001f0a
def encode_ipv4(s):
    if isinstance(s, str):
        return hex_str_with_pad(struct.unpack("I", socket.inet_aton(s))[0], 8)

    return None

# 0xfa001f0a => 10.31.0.250
def decode_ipv4(s):
    if s == "0x00000000":
        return ""

    return socket.inet_ntoa(struct.pack("<L", int(s, 16)))

# true => 0x01 / false => 0x00 / None => None
def encode_checkbox(s):
    if s is None:
        return None

    return "0x01" if s else "0x00"

# 0x01 => true
def decode_checkbox(s):
    return s == "0x01"

# [1, 3, 4] --> [1, 0, 1, 1]
def ports_to_flag_list(ports, fill=0):       ########### not used anymore
    if not isinstance(ports, list):
        return None

    if not fill and len(ports):
        fill = max(ports)

    flag_list = [0] * fill
    for i in ports:
        flag_list[i-1] = 1

    return flag_list

# (0x)1234 --> 4
def hex_value_len(s):
    if not isinstance(s, str):
        return None

    if s.startswith("0x"):
        return len(s)-2

    return len(s)

# decode version
#   (0x)322e3138 --> 2.18
#   strip "p" (for primary) : 2.16p -> 2.16
def decode_swos_version(s):
    return float(decode_string(s).replace("p", ""))
