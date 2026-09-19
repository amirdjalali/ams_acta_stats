from pymongo import MongoClient


client = MongoClient("mongodb://localhost:27017/")  # or your Atlas connection string
db = client["admin"]
collection = db["amsacta_documenti"]

# Run the same aggregation from before
results = collection.aggregate([
    {"$group": {"_id": "$subject", "count": {"$sum": 1}}}
])

for doc in results:
    print(doc)




import pandas as pd

results = list(collection.aggregate([
    {"$group": {"_id": "$subject", "count": {"$sum": 1}}}
]))
df = pd.DataFrame(results)
df.rename(columns={"_id": "subject"}, inplace=True)