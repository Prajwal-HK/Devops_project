from pymongo import MongoClient
import sys

try:
    client = MongoClient('mongodb://localhost:27017/', serverSelectionTimeoutMS=2000)
    client.server_info() # trigger a connect
    print("SUCCESS: Connected to MongoDB")
    db = client['crms_db']
    collections = db.list_collection_names()
    print(f"Collections in crms_db: {collections}")
    for coll in collections:
        count = db[coll].count_documents({})
        print(f" - {coll}: {count} documents")
except Exception as e:
    print(f"FAILURE: Could not connect to MongoDB: {e}")
    sys.exit(1)
