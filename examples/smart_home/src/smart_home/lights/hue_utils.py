from phue import Bridge

from smart_home.settings import settings


def get_bridge() -> Bridge:
    """Connect without saving credentials to disk; SDK errors propagate as tool errors."""
    return Bridge(
        ip=settings.hue_bridge_ip,
        username=settings.hue_bridge_username,
        save_config=False,
    )
