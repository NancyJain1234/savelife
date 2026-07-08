import os
from urllib.parse import quote_plus

from dotenv import load_dotenv

load_dotenv()


class Config:
    SECRET_KEY = os.environ.get("SECRET_KEY")
    MONGO_USERNAME = os.environ.get("MONGO_USERNAME")
    MONGO_PASSWORD = quote_plus(os.environ.get("MONGO_PASSWORD", ""))
    MONGO_CLUSTER = os.environ.get("MONGO_CLUSTER")
    MONGO_DB = os.environ.get("MONGO_DB", "savelife")
    MONGO_URI = (
        f"mongodb+srv://{MONGO_USERNAME}:{MONGO_PASSWORD}"
        f"@{MONGO_CLUSTER}/{MONGO_DB}?retryWrites=true&w=majority"
    )
