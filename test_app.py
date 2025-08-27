from pymongo import MongoClient
from urllib.parse import quote_plus

# Your actual MongoDB credentials
db_username = quote_plus("savelife")       # MongoDB Atlas username
db_password = quote_plus("Nancy@123")      # MongoDB Atlas password

# Substitute the variables into the URI
MONGO_URI = f"mongodb+srv://{db_username}:{db_password}@savelife.ua5gyhw.mongodb.net/?retryWrites=true&w=majority&appName=savelife"

try:
    client = MongoClient(MONGO_URI)
    db = client.get_database("savelife")
    print("Collections:", db.list_collection_names())
except Exception as e:
    print("Connection Error:", e)
