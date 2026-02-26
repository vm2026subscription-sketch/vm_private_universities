from pymongo import MongoClient

# Connect to MongoDB
client = MongoClient("mongodb://localhost:27017/")
db = client["mvc_admissions"]

# Check users collection
users = list(db["users"].find({}, {"_id": 0, "password": 0}))
print("Users in database:")
for user in users:
    print(f"  - {user['name']} ({user['email']})")

# Check contacts collection  
contacts = list(db["contacts"].find({}, {"_id": 0}))
print("\nContact messages in database:")
for contact in contacts:
    print(f"  - From: {contact['name']} ({contact['email']})")
    print(f"    Message: {contact['message'][:50]}...")
