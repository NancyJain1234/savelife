from urllib.parse import quote_plus
class Config:
    SECRET_KEY = 'your_secret_key'
    MONGO_URI = "mongodb+srv://<savelife>:<Nancy@123>@cluster0.ua5gyhw.mongodb.net/lifeline_connect?retryWrites=true&w=majority&tls=true"


    # MongoDB
    MONGO_USERNAME = "savelife"
    MONGO_PASSWORD = quote_plus("Nancy@123")  # encode special chars
    MONGO_CLUSTER = "savelife.ua5gyhw.mongodb.net"
    MONGO_DB = "savelife"
    MONGO_URI = f"mongodb+srv://{MONGO_USERNAME}:{MONGO_PASSWORD}@{MONGO_CLUSTER}/{MONGO_DB}?retryWrites=true&w=majority"
