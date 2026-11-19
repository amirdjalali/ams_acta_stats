from pymongo import MongoClient
import requests
import json
import os
import pandas as pd
import matplotlib.pyplot as plt
import plotly.express as px
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import plotly.io as pio
import numpy as np
from itertools import cycle

OWN_ROR = "01111rn36"

def connect_to_db(client_url, db_name, collection_name):
    print("Connecting to MongoDB...")
    client = MongoClient()  # or your Atlas connection string
    db = client["admin"]
    collection = db["amsacta_documenti"]
    return collection

def get_ror_ids(collection, type="dataset", start_year=0, end_year=9999, only_with_ror=True):
    start_date = f"{start_year:04d}-01-01"
    end_date = f"{end_year}-12-31 23:59:59"  # inclusive, and avoids a "10000-01-01" string comparison

    pipeline = [
        {
            "$match": {
                "type": type,
                "datestamp": {"$gte": start_date, "$lte": end_date}
            }
        },
        {
            "$project": {
                "_id": 0,
                "eprintid": 1,
                "date": {"$substrCP": ["$datestamp", 0, 10]},  # "2026-09-07 13:30:34" -> "2026-09-07"
                "rors": {
                    "$setUnion": [[], {          # setUnion removes duplicates
                        "$filter": {
                            "input": {
                                "$map": {
                                    "input": {"$ifNull": ["$creators", []]},
                                    "as": "c",
                                    "in": "$$c.ror"
                                }
                            },
                            "as": "r",
                            "cond": {"$and": [
                                {"$ne": ["$$r", None]},
                                {"$ne": ["$$r", ""]}
                            ]}
                        }
                    }]
                }
            }
        }
    ]

    if only_with_ror:
        pipeline.append({"$match": {"rors": {"$ne": []}}})

    pipeline.append({"$sort": {"date": 1}})

    results = list(collection.aggregate(pipeline))
    df = pd.DataFrame(results, columns=["eprintid", "date", "rors"])
    return df


def clean_ror(ror_url):
    return str(ror_url).replace("https://ror.org/", "").strip()

def get_coordinates(ror):
    """Returns (lat, lon, name) for a ROR id, or (None, None, ror) on failure."""
    try:
        r = requests.get(f"https://api.ror.org/v2/organizations/{ror}", timeout=10)
        r.raise_for_status()
        data = r.json()
        geo = data["locations"][0]["geonames_details"]
        name = next(
            (n["value"] for n in data.get("names", []) if "ror_display" in n.get("types", [])),
            ror,
        )
        return geo["lat"], geo["lng"], name
    except (requests.RequestException, KeyError, IndexError, TypeError) as e:
        print(f"Could not get coordinates for {ror}: {e}")
        return None, None, ror

def make_coordinates_dict(rors):
    if os.path.exists("coordinates.json"):
        with open("coordinates.json", "r") as file:
            coordinates = json.load(file)
    else: 
        coordinates = {}
        for ror in rors.unique():
            lat, lon, name = get_coordinates(ror)
            coordinates[ror] = {"lat": lat, "lon": lon, "name": name}
        with open("coordinates.json", "w") as file:
            json.dump(coordinates, file, indent=4)
    return coordinates

def plot_collaboration_map(df):
    # df is the output of get_ror_ids: eprintid, date, rors (list)
    df = (df.explode("rors")
            .rename(columns={"rors": "ror"})
            .dropna(subset=["ror"]))
    df["ror"] = df["ror"].map(clean_ror)
    df = df[df["ror"] != ""]

    coords = make_coordinates_dict(df["ror"])
    
    df["lat"] = df["ror"].map(lambda r: coords[r]["lat"])
    df["lon"] = df["ror"].map(lambda r: coords[r]["lon"])
    df["name"] = df["ror"].map(lambda r: coords[r]["name"])
    df = df.dropna(subset=["lat", "lon"])
    df = df[df["ror"] != OWN_ROR]
    
    # step 1: one row per institution, with its own eprintids
    df_inst = (df.groupby(["lat", "lon", "name"])
                .agg(eprintids=("eprintid", lambda s: sorted(set(s))))
                .reset_index())

    def inst_block(row, max_ids=15):
        ids = row["eprintids"]
        shown = ", ".join(map(str, ids[:max_ids]))
        if len(ids) > max_ids:
            shown += f", ... (+{len(ids) - max_ids})"
        return f"<b>{row['name']}</b> ({len(ids)})<br>{shown}"

    df_inst["block"] = df_inst.apply(inst_block, axis=1)

    # step 2: one row per location, blocks stacked in the hover
    df_map = (df_inst.groupby(["lat", "lon"])
                    .agg(hover=("block", "<br><br>".join))
                    .reset_index())

    # the bubble size still counts unique datasets per location
    counts = (df.groupby(["lat", "lon"])["eprintid"]
                .nunique()
                .rename("count")
                .reset_index())
    df_map = df_map.merge(counts, on=["lat", "lon"])

    fig = px.scatter_map(
        df_map,
        lat="lat",
        lon="lon",
        size="count",
        custom_data=["hover"],
        zoom=1,
        center={"lat": 20, "lon": 0},
    )
    fig.update_traces(hovertemplate="%{customdata[0]}<extra></extra>")
    fig.update_layout(map_style="carto-positron")   # light, minimal (great for data overlays)
    # other options:
    # carto-positron
    # "carto-darkmatter"  dark minimal
    # "white-bg"          blank white background, no tiles at all
    # "open-street-map"   what you're using now
    return fig, df_map

if __name__ == "__main__":
    collection = connect_to_db("mongodb://localhost:27017/",  "admin", "amsacta_documenti")
    df = get_ror_ids(collection, "dataset", 2025, 2026)
    print(len(df))                               # all datasets in range
    print((df["rors"].apply(len) > 0).sum())     # datasets with at least one ror
    print(df["rors"].apply(len).value_counts())   # how many datasets have 0, 1, 2... rors
    print(df["rors"].explode().dropna().nunique())  # unique rors before any API call
    types_dates = {
        "type": "dataset",
        "datestamp": {"$gte": "2025-01-01", "$lte": "2026-12-31 23:59:59"},
    }
    print("type+date only:", collection.count_documents(types_dates))
    print("with creators.ror:", collection.count_documents({**types_dates, "creators.ror": {"$nin": [None, ""], "$exists": True}}))
    print("with creator.ror:", collection.count_documents({**types_dates, "creator.ror": {"$nin": [None, ""], "$exists": True}}))
    fig, df_map = plot_collaboration_map(df)
    fig.show()