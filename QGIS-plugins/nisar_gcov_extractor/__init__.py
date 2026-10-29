def classFactory(iface):
    """Load NisarSubsetPlugin class from main.py."""
    from .main import NisarSubsetterPlugin
    return NisarSubsetterPlugin(iface)