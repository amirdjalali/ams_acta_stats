from pymongo import MongoClient
import pandas as pd
import matplotlib.pyplot as plt
import plotly.express as px
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import plotly.io as pio



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

def get_types(collection):
    pipeline = [
        {
            "$match": {
                "datestamp": { "$exists": True, "$ne": None },
                "type": { "$exists": True, "$ne": None }
            }
        },
        {
            "$group": {
                "_id": {
                    "year": { "$year": { "$toDate": "$datestamp" } },
                    "type": "$type"
                },
                "count": { "$sum": 1 }
            }
        },
        {
            "$sort": { "_id.year": 1, "count": -1 }
        }
    ]

    results = list(collection.aggregate(pipeline))
    df = pd.json_normalize(results).rename(columns={
        "_id.year": "year",
        "_id.type": "type"
    })
    print(df)
    return df

def get_filesize(collection):

    pipeline = [
        {
            "$match": {
                "type": "dataset",
                "datestamp": { "$exists": True, "$ne": None }
            }
        },
        {
            "$unwind": "$documents"
        },
        {
            "$unwind": "$documents.files"
        },
        {
            "$group": {
                "_id": {
                    "$year": {
                        "$toDate": "$datestamp"
                    }
                },
                "total_filesize": {
                    "$sum": "$documents.files.filesize"
                }
            }
        },
        {
            "$sort": {
                "_id": -1
            }
        }
    ]

    results = list(collection.aggregate(pipeline))
    df = pd.json_normalize(results).astype({
        "_id": int,
        "total_filesize": "int64"
    }).rename(columns={"_id": "year"}).sort_values("year", ascending=True)
    
    return df

def get_funding_info(collection, param, start_year, end_year):
    start_date=f"{start_year}-01-01"
    end_date=f"{end_year+1}-01-01"
    pipeline = [
        {
            "$match": {
                "datestamp": {
                    "$gt": start_date,
                    "$lt": end_date
                },
                "type": "dataset",        
                param: { "$exists": True, "$ne": None }
            }
        },
        {
            "$project": { 
                param: 1,
                "_id": 0
            }
        },
        {
            "$group": {
                "_id": f"${param}",
                "count": {
                    "$sum": 1
                }
            }
        },
        {
            "$sort": {
                "count": -1
            }
        }
    ]

    results = list(collection.aggregate(pipeline))
    df = pd.json_normalize(results).rename(columns={"_id": param})
    print(df)
    return df

def get_creators(collection, start_year, end_year):
    start_date=f"{start_year}-01-01"
    end_date=f"{end_year+1}-01-01"
    pipeline = [
        {
            "$match": {
                "datestamp": {
                    "$gt": start_date,
                    "$lt": end_date
                },
                "type": "dataset",
                "creators": { "$exists": True, "$ne": None }
            }
        },
        {
            "$unwind": "$creators"
        },
        {
            "$group": {
                "_id": {
                    "family": "$creators.name.family",
                    "given": "$creators.name.given"
                },
                "count": { "$sum": 1 }
            }
        },
        {
            "$sort": { "count": -1 }
        }
    ]

    results = list(collection.aggregate(pipeline))
    df = pd.json_normalize(results).rename(columns={
        "_id.family": "family",
        "_id.given": "given"
    })
    print(df)
    return df

def get_related_id(collection):
    pipeline = [
        {
            "$match": {
                "type": "dataset",
                "datestamp": { "$exists": True, "$ne": None }
            }
        },
        {
            "$group": {
                "_id": {
                    "year": { "$year": { "$toDate": "$datestamp" } },
                    "has_relatedid": {
                        "$cond": {
                            "if": { "$gt": [{ "$size": { "$ifNull": ["$relatedid", []] } }, 0] },
                            "then": True,
                            "else": False
                        }
                    }
                },
                "count": { "$sum": 1 }
            }
        },
        {
            "$sort": { "_id.year": 1 }
        }
    ]

    results = list(collection.aggregate(pipeline))
    df = pd.json_normalize(results).rename(columns={
        "_id.year": "year",
        "_id.has_relatedid": "has_relatedid"
    })
    print(df)
    return df

    results = list(collection.aggregate(pipeline))
    df = pd.json_normalize(results).rename(columns={"_id": "year"})
    print(df)

def export_by_year(df, date_list=None):
    pivot = df.pivot(
        index="_id.subject",
        columns="_id.year",
        values="count",
    ).fillna(0).astype(int)
    pivot = pivot[date_list] if date_list else pivot
    pivot.reset_index().to_csv("subjects.csv", index=False)
    return pivot

def plot_pie_chart(df, param, threshold=0, start_year=None, end_year=None):
    date_list = range(start_year, end_year+1)
    df = df.loc[df["_id.year"].isin(date_list)]
    df = df.rename(columns={"_id.subject": "subject"})
    df["macro_sector"] = df.apply(lambda row: row.subject.split("-")[0], axis=1)
    print(df)
    counts_macro_sectors = df.groupby("macro_sector")["count"].sum()
    counts_subjects = df.groupby("subject")["count"].sum()

    macro_sectors_dict = counts_macro_sectors.to_dict()
    subjects_dict = counts_subjects.to_dict()
    print(subjects_dict)
    df_clean = df.copy()
    # remove macro_sector if count < min
    df_clean["macro_sector"] = [label if macro_sectors_dict[label] > threshold else "other" for label in df["macro_sector"]]
    # remove also subject if macro sector is other
    df_clean.loc[df_clean["macro_sector"] == "other", "subject"] = "other"
    print(df)
    # remove subject is subject count is lesser than min
    df_clean["subject"] = [label if subjects_dict.get(label, 0) > threshold else "other" for label in df_clean["subject"]]
    print(df_clean)
    fig2 = px.sunburst(df_clean, path=["macro_sector", "subject"], values="count", title=f"Subjects Distribution, {start_year}, {end_year}")
    #fig2.show()  # opens in browser
    df_clean.to_csv(f"{param}_{start_year}_{end_year}.csv", index=False, encoding="utf-8")
    return fig2

def plot_size_historgram(df, min_year=None, max_year=None):
    df_filtered = df[(df["year"] >= min_year) & (df["year"] <= max_year)]
    df_filtered["total_filesize"] = df_filtered["total_filesize"] / (1024 ** 3)
    fig = px.histogram(
        df_filtered,
        x=df_filtered["year"].astype(str),
        y="total_filesize",
        title="Total Filesize by Year (GB)",
        log_y=True
    )
    fig.update_yaxes(
        title_text="",        # remove y axis label
        tickmode="array",
        tickvals=[.001, .01, .1, 1, 10, 100, 1000, 10000]
    )
    df_filtered.to_csv("sizes.csv", index=False, encoding="utf-8")
    #fig.show()
    return fig

def plot_histogram(df, min_year=0, max_year=9999, type_filter=None, filename="documents"):
    df_filtered = df[(df["year"] >= min_year) & (df["year"] <= max_year)]
    if type_filter:
        df_filtered = df_filtered[df_filtered["type"] == type_filter]
    fig = px.bar(
        df_filtered,
        x=df_filtered["year"].astype(str),
        y="count",
        color="type",
        title=f"Documents by Year, {min_year}, {max_year}" + (f" — {type_filter}" if type_filter else ""),
        barmode="stack"
        )
    df_filtered.to_csv(f"{filename}_{min_year}-{max_year}" + (f"_{type_filter}" if type_filter else "") + ".csv", index=False, encoding="utf-8")
    return fig


def plot_funding_treemap(df, param, min_year="", max_year="", threshold=1):
    df[param] = df.apply(
        lambda r: r[param] if r["count"] > threshold else "Other", axis=1
    )
    # merge all Other rows into one
    df_grouped = df.groupby(param)["count"].sum().reset_index()
    fig = px.treemap(
        df_grouped,
        path=[param],
        values="count",
        title=f"Funding information ({param}), {min_year}, {max_year}"
    )
    df_grouped.to_csv(f"{param}_{min_year}-{max_year}.csv", index=False, encoding="utf-8")
    #fig.show()
    return fig

def plot_creators(df, min_year="", max_year="", top_n=100):
     # combine family and given into one label
    df["creator"] = df["given"] + " " + df["family"]

    df_grouped = df.groupby("creator")["count"].sum().reset_index()
    df_grouped = df_grouped.nlargest(top_n, "count")

    fig = px.treemap(
        df_grouped,
        path=["creator"],
        values="count",
        title=f"Top {top_n} creators, {min_year}, {max_year}"
    )

    df_grouped.to_csv(f"top_{top_n}_creators_{min_year}-{max_year}.csv", index=False, encoding="utf-8")
    #fig.show()
    return fig

if __name__ == "__main__":
    start_years = [2017, 2020, 2023]
    
    collection = connect_to_db("mongodb://localhost:27017/",  "admin", "amsacta_documenti")

    types = get_types(collection)
    types_plot = plot_histogram(types, 2017, 2025)
    datasets_plot = plot_histogram(types, 2017, 2025, type_filter="dataset")
    sizes = get_filesize(collection)
    gbs = plot_size_historgram(sizes, 2017, 2025)
    related = get_related_id(collection)
    related = related.rename(columns={"has_relatedid": "type"})
    related["type"] = related["type"].map({True: "has relatedid", False: "no relatedid"})
    related_plot = plot_histogram(related, min_year=2017, max_year=2025, filename="relatedid")
    
    with open("dashboard.html", "w") as f:
        f.write("""
                <html>
                <head>
                <style>
                    body {
                        font-family: Arial, sans-serif;
                        margin: 40px;
                        background-color: #f9f9f9;
                    }
                    h1 {
                        font-size: 2em;
                        color: #333;
                        border-bottom: 2px solid #ccc;
                        padding-bottom: 10px;
                        margin-top: 40px;
                    }
                    h2 {
                        font-size: 1.5em;
                        color: #555;
                        margin-top: 30px;
                    }
                </style>
                </head>
                <body>
                """)

        f.write("<h1>Documenti per tipologia</h1>")
        f.write(types_plot.to_html(full_html=False, include_plotlyjs="cdn"))
        f.write(datasets_plot.to_html(full_html=False, include_plotlyjs=False))
        f.write("<h1>Dataset con collegamento a pubblicazione</h1>")
        f.write(related_plot.to_html(full_html=False, include_plotlyjs=False))
        f.write("<h1>Volume di dati</h1>")
        f.write(gbs.to_html(full_html=False, include_plotlyjs=False))



        f.write("<h1>Settori disciplinari</h1>")
        for start_year in start_years:
            end_year = start_year + 2
            subjects = get_subjects(collection)
            threshold = 5 if start_year > 2019 else 1
            subjects_plot = plot_pie_chart(df=subjects, param="subject", threshold=threshold, start_year=start_year, end_year=end_year)
            f.write(subjects_plot.to_html(full_html=False, include_plotlyjs=False))

        f.write("<h1>Progetti</h1>")
        for start_year in start_years:
            end_year = start_year + 2
            projects = get_funding_info(collection, "projectacronym", start_year, end_year)
            projects_plot = plot_funding_treemap(projects, "projectacronym", start_year, end_year)
            f.write(projects_plot.to_html(full_html=False, include_plotlyjs=False))

        f.write("<h1>Enti finanziatori</h1>")
        for start_year in start_years:
            end_year = start_year + 2
            funders = get_funding_info(collection, "funder", start_year, end_year)
            funders_plot = plot_funding_treemap(funders, "funder", start_year, end_year)
            f.write(funders_plot.to_html(full_html=False, include_plotlyjs=False))

        f.write("<h1>Creatori</h1>")
        for start_year in start_years:
            end_year = start_year + 2
            creators = get_creators(collection, start_year, end_year)
            creators_plot = plot_creators(creators, start_year, end_year, 50)
            f.write(creators_plot.to_html(full_html=False, include_plotlyjs=False))

        
        f.write("</body></html>")


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

