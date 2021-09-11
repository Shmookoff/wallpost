class PrefixGreaterThan3(Exception): pass
class ChannelNotSpecified(Exception): pass
class ChannelForbiddenWebhooks(Exception): pass
class MaximumWebhooksReached(Exception): pass
class VkIdNotSpecified(Exception): pass
class CouldNotFindWall(Exception):
    def __init__(self, grp, usr):
        self.grp_msg = grp['error_msg']
        self.usr_msg = usr['error_msg']
class WallIdBadArgument(Exception): pass
class SubExists(Exception): pass
class NoSubs(Exception): pass
class NotSub(Exception): pass
class NotAuthenticated(Exception): pass
class WallClosed(Exception): pass
class MsgTooLong(Exception): pass