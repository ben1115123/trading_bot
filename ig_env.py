import os


def get_ig_credentials() -> tuple[str, str, str, str]:
    """Returns (username, password, api_key, acc_type) based on IG_ACC_TYPE
    env var. Default LIVE -- removing IG_ACC_TYPE from .env safely reverts
    to live. DEMO mode uses IG_DEMO_USERNAME/IG_DEMO_PASSWORD -- this
    account's demo login is separate from live -- falling back to
    IG_USERNAME/IG_PASSWORD if the demo-specific vars are absent.
    """
    acc_type = os.getenv("IG_ACC_TYPE", "LIVE").upper()
    if acc_type == "DEMO":
        username = os.getenv("IG_DEMO_USERNAME") or os.getenv("IG_USERNAME")
        password = os.getenv("IG_DEMO_PASSWORD") or os.getenv("IG_PASSWORD")
        api_key  = os.getenv("IG_DEMO_API_KEY")
    else:
        username = os.getenv("IG_USERNAME")
        password = os.getenv("IG_PASSWORD")
        api_key  = os.getenv("IG_API_KEY")
    return username, password, api_key, acc_type
