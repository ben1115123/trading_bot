import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from trading_ig import IGService
from dotenv import load_dotenv
import os

from ig_env import get_ig_credentials

load_dotenv()

username, password, api_key, acc_type = get_ig_credentials()

ig_service = IGService(
    username,
    password,
    api_key,
    acc_type=acc_type
)

ig_service.create_session()

result = ig_service.search_markets("btc")

print(result)