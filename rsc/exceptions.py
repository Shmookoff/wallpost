from discord import TextChannel

class CouldNotFindWall(Exception):
    def __init__(self, grp: dict, usr: dict):
        self.grp_msg = grp['error_msg']
        self.usr_msg = usr['error_msg']
class SubExists(Exception):
    def __init__(self, chn: TextChannel, wall_id: int):
        self.chn = chn
        self.wall_id = wall_id
class NoSubs(Exception):
    def __init__(self, chn: TextChannel):
        self.chn = chn
class NotAuthenticated(Exception): pass
class MsgTooLong(Exception):
    def __init__(self, msg: str):
        self.msg = msg