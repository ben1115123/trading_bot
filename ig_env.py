import os


def get_ig_credentials() -> tuple[str, str]:
    """Returns (api_key, acc_type) based on IG_ACC_TYPE env var.
    Default LIVE — removing IG_ACC_TYPE from .env safely reverts to live.
    """
    acc_type = os.getenv("IG_ACC_TYPE", "LIVE").upper()
    if acc_type == "DEMO":
        api_key = os.getenv("IG_DEMO_API_KEY")
    else:
        api_key = os.getenv("IG_API_KEY")
    return api_key, acc_type
