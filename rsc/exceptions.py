from discord.ext.commands import BotMissingPermissions

from discord import TextChannel


class SubscriptionChannelMissingPermissions(Exception):
    def __init__(self, missing_perms, channel: TextChannel):
        self.missing_perms = missing_perms

        missing = [perm.replace('_', ' ').replace('guild', 'server').title() for perm in missing_perms]

        if len(missing) > 2:
            fmt = '{}, and {}'.format(", ".join(missing[:-1]), missing[-1])
        else:
            fmt = ' and '.join(missing)
        message = f'Bot requires {fmt} permission(s) in {channel.mention} to enable Channel Subscriptions.'
        self.message = message

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