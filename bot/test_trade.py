from trading_ig import IGService
from dotenv import load_dotenv
import os

load_dotenv()

username = os.getenv("IG_USERNAME")
password = os.getenv("IG_PASSWORD")
api_key = os.getenv("IG_API_KEY")

ig_service = IGService(
    username,
    password,
    api_key,
    acc_type="DEMO"
)

ig_service.create_session()

epic = "CS.D.CFDGOLD.BMU.IP"

response = ig_service.create_open_position(
    currency_code="USD",
    direction="BUY",
    epic=epic,
    expiry="-",
    force_open=True,
    guaranteed_stop=False,
    order_type="MARKET",
    size=0.1,

    level=None,
    limit_level=None,
    stop_level=None,

    limit_distance=None,
    stop_distance=10,

    quote_id=None,
    trailing_stop=False,
    trailing_stop_increment=None
)

print(response)