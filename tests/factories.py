"""Builders for Steam schema/data dicts shaped like real UserGameStats files."""

APPID = "100"
USERID = 12345


def ach(name, operand=None, max_val=None):
    a = {"name": name, "display": {"name": {"english": name}}}
    if operand is not None:
        a["progress"] = {"min_val": 0, "max_val": max_val, "value": {"operation": "statvalue", "operand1": operand}}
    return a


def make_schema():
    return {
        APPID: {
            "gamename": "Test Game",
            "version": 1,
            "stats": {
                "1": {
                    "type": "ACHIEVEMENTS",
                    "bits": {
                        "0": ach("ACH_PLAIN"),
                        "1": ach("ACH_KILLS_10", "kills", 10),
                        "2": ach("ACH_KILLS_100", "kills", 100),
                        "3": ach("ACH_WALK_1000", "distance", 1000),
                        "4": ach("ACH_OTHER"),
                    },
                },
                "2": {"type": "INT", "name": "kills", "min": 0, "default": 0},
                "3": {"type": "FLOAT", "name": "distance", "default": 0},
                "4": {"type": "INT", "name": "unrelated", "default": 0},
            },
        }
    }


def make_data(earned=None, kills=0, distance=0.0, unrelated=7):
    """earned: {bit_index_str: unix_time}"""
    earned = earned or {}
    bitmask = 0
    for i in earned:
        bitmask |= 1 << int(i)
    return {
        "cache": {
            "crc": 123,
            "PendingChanges": 0,
            "1": {"data": bitmask, "AchievementTimes": dict(earned)},
            "2": {"data": kills},
            "3": {"data": distance},
            "4": {"data": unrelated},
        }
    }
