# find.py
from pymongo import MongoClient

def find_donors(blood_group, city, state):
    client = MongoClient("mongodb+srv://<USERNAME>:<PASSWORD>@<CLUSTER>/<DB>?retryWrites=true&w=majority")
    db = client['savelife']
    donors_collection = db['donors']

    donors = list(donors_collection.find({
        "blood_group": blood_group,
        "city": city,
        "state": state
    }, {"_id": 0, "name": 1, "email": 1, "phone": 1, "city": 1, "state": 1}))

    return donors
