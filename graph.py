from pymongo import MongoClient
import pandas as pd
import matplotlib.pyplot as plt
import plotly.express as px
import plotly.graph_objects as go



def connect_to_db(client_url, db_name, collection_name):

    client = MongoClient()  # or your Atlas connection string
    db = client["admin"]
    collection = db["amsacta_documenti"]
    return collection

def get_subjects(collection):
    pipeline = [
        {
            "$match": {
                "type": "dataset",
                 "datestamp": { "$exists": True, "$ne": None }
            }
        },
        {
            "$addFields": {
                "subjects": {
                    "$cond": {
                        "if": { "$isArray": "$subjects" },
                        "then": "$subjects",
                        "else": { "$concatArrays": [["$subjects"]] }
                    }
                }
            }
        },
        { "$unwind": "$subjects" },
        {
            "$group": {
                "_id": {
                    "year": { "$year": { "$toDate": "$datestamp" } },
                    "subject": "$subjects"
                },
                "count": { "$sum": 1 }
            }
        },
        { "$sort": { "count": -1 } }
    ]

    results = list(collection.aggregate(pipeline))
    df = pd.json_normalize(results).astype({
        "count": int,
        "_id.year": int,
        "_id.subject": str
    })
    
    return df

def export_by_year(df, date_list=None):
    pivot = df.pivot(
        index="_id.subject",
        columns="_id.year",
        values="count",
    ).fillna(0).astype(int)
    pivot = pivot[date_list] if date_list else pivot
    pivot.reset_index().to_csv("subjects.csv", index=False)
    return pivot

def plot_pie_chart(df, param, min=0, date_list=None):
    df = df.loc[df["_id.year"].isin(date_list)]
    df = df.rename(columns={"_id.subject": "subject"})
    print(df)
    df["macro_sector"] = df.apply(lambda row: row.subject.split("-")[0], axis=1)
    counts = df["macro_sector"].value_counts()
    print(counts)
    counts.index = [label if count >= min else "Other" for label, count in counts.items()]
    fig = px.pie(
        values=counts.values,
        names=counts.index,
        title=f"Subjects Distribution, {date_list}"
    )
    fig2 = px.sunburst(df, path=["macro_sector", "subject"], title=f"Subjects Distribution, {date_list}")
    fig2.show()  # opens in browser
    return counts.groupby(counts.index).sum()



if __name__ == "__main__":
    collection = connect_to_db("mongodb://localhost:27017/",  "admin", "amsacta_documenti")
    subjects = get_subjects(collection)
    #print(subjects)
    by_year = export_by_year(subjects)
    #print(by_year)
    pie_subjects = plot_pie_chart(df=subjects, param="subject", min=2, date_list=[2023,2024,2025])
    #print(pie_subjects)




# counts = df["subjects"].value_counts()
# counts.index = [label if count >= 3 else "Other" for label, count in counts.items()]
# counts = counts.groupby(counts.index).sum()

# print(counts)

# fig, ax = plt.subplots(figsize=(12, 8))

# wedges, texts = ax.pie(
#     counts.values,
#     labels=counts.index,
#     #autopct="%1.1f%%",
#     startangle=140,
#     pctdistance=1.2,
#     labeldistance=1.2,
# )

# # for text in texts:
# #     x, y = text.get_position()
# #     text.set_position((x - 0.1, y))  # change 0.1 to more or less offset

# ax.set_title("Subjects Distribution")
# plt.tight_layout()
# plt.show()

