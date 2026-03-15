import requests
import os
import dotenv
import pprint

dotenv.load_dotenv()

APP_URL = os.getenv("HTTP_URL")
TOKEN = os.getenv("CANVAS_TOKEN")

API_URL = f"{APP_URL}/dashboard/dashboard_cards"

headers = {
    "Authorization": f"Bearer {TOKEN}"
}

response = requests.get(API_URL, headers=headers)
data = response.json()


print("Dashboard Cards:")
pprint.pprint(data)