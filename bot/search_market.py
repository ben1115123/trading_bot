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

result = ig_service.search_markets("us tech 100")

print(result)