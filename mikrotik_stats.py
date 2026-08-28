#!/usr/bin/env python3


from mikrotik_swos import utils
from mikrotik_swos.swostab import Swostab


PAGE = "/stats.b"


class Mikrotik_Stats(Swostab):
    def _load_tab_data(self):
        self._page = PAGE
        self._data = utils.mikrotik_to_json(self._get(PAGE).text)

    def get_stats(self):
        pass
    def get_errors(self):
        pass
    def get_hist(self):
        pass
    
    def show(self):
        print("snmp tab")
        print("* enabled: {}" . format(utils.decode_checkbox(self._data["en"])))
        print("* community: {}" . format(utils.decode_string(self._data["com"])))
        print("* contact: {}" . format(utils.decode_string(self._data["ci"])))
        print("* location: {}" . format(utils.decode_string(self._data["loc"])))
        print("")
