from pymongo import MongoClient
import pandas as pd
import matplotlib.pyplot as plt
import plotly.express as px
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import plotly.io as pio
from itertools import cycle

OUT_DIR = "out"

def connect_to_db(client_url, db_name, collection_name):

    client = MongoClient()  # or your Atlas connection string
    db = client["admin"]
    collection = db["amsacta_documenti"]
    return collection

def get_subjects_or_structures(collection, type="subjects"):
    singular = type[:-1]
    pipeline = [
        {
            "$match": {
                "type": "dataset",
                 "datestamp": { "$exists": True, "$ne": None }
            }
        },
        {
            "$addFields": {
                type: {
                    "$cond": {
                        "if": { "$isArray": f"${type}" },
                        "then": f"${type}",
                        "else": { "$concatArrays": [[f"${type}"]] }
                    }
                }
            }
        },
        { "$unwind": f"${type}" },
        {
            "$group": {
                "_id": {
                    "year": { "$year": { "$toDate": "$datestamp" } },
                    singular: f"${type}"
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
        f"_id.{singular}": str
    }).rename(columns={f"_id.{singular}": singular, "_id.year": "year"})
    
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
        "_id": "int64",
        "total_filesize": "int64"
    }).rename(columns={"_id": "year"}).sort_values("year", ascending=True)
    
    return df

def get_filesizes_per_dataset(collection):

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
            "$group": {     # sums individual files per record
                "_id": {
                    "year": { "$year": { "$toDate": "$datestamp" } },
                    "record": "$_id"
                },
                "total_filesize": { "$sum": "$documents.files.filesize" }
            }
        },
        {
            "$group": {     # calculates median across records per year
                "_id": "$_id.year",
                "median_dataset_size": { "$median": { "input": "$total_filesize", "method": "approximate" } }
            }
        },
        {
            "$sort": { "_id": 1 }
        }
    ]

    results = list(collection.aggregate(pipeline))
    df = pd.json_normalize(results).astype({
        "_id": "int64",
        "median_dataset_size": "int64"
    }).rename(columns={"_id": "year"}).sort_values("year", ascending=True)
    
    return df

def get_grouped_median_sizes(collection, bins=None):
    if bins is None:
        bins = [2015, 2020, 2023, 2026]
    
    branches = []
    for i in range(len(bins) - 1):
        branches.append({
            "case": { "$and": [
                { "$gte": ["$_id.year", bins[i]] },
                { "$lt": ["$_id.year", bins[i+1]] }
            ]},
            "then": f"{bins[i]}-{bins[i+1]}"
        })

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
                    "year": { "$year": { "$toDate": "$datestamp" } },
                    "record": "$_id"
                },
                "total_filesize": { "$sum": "$documents.files.filesize" }
            }
        },
        {
            "$addFields": {
                "year_range": {
                    "$switch": {
                        "branches": branches,
                        "default": "other"
                    }
                }
            }
        },
        {
            "$group": {
                "_id": "$year_range",
                "median_dataset_size": { "$median": { "input": "$total_filesize", "method": "approximate" } }
            }
        },
        {
            "$sort": { "_id": 1 }
        }
    ]

    results = list(collection.aggregate(pipeline))
    df = pd.json_normalize(results).astype({
        "_id": str,
        "median_dataset_size": "int64"
    }).rename(columns={"_id": "year_range"}).sort_values("year_range", ascending=True)

    return df

def get_funding_info(collection, param, start_year, end_year, get_all=False):
    start_date=f"{start_year}-01-01"
    end_date=f"{end_year+1}-01-01"
    if get_all:
        pipeline = [
            {
                "$match": {
                    "datestamp": {
                        "$gt": start_date,
                        "$lt": end_date
                    },
                    "type": "dataset"
                }
            },
            {
                "$addFields": {
                    param: {
                        "$ifNull": [f"${param}", "None"]
                    }
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
    else:        
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

def plot_subject_chart(df, param, 
                       threshold=0, 
                       start_year=None, 
                       end_year=None, 
                       color_map=None, 
                       pattern_map=None):
    
    date_list = range(start_year, end_year+1)
    df = df.loc[df["year"].isin(date_list)]
    df["macro_sector"] = df.apply(lambda row: row.subject.split("-")[0], axis=1)
    counts_macro_sectors = df.groupby("macro_sector")["count"].sum()
    counts_subjects = df.groupby("subject")["count"].sum()

    macro_sectors_dict = counts_macro_sectors.to_dict()
    subjects_dict = counts_subjects.to_dict()
    df_clean = df.copy()
    # remove macro_sector if count < min
    df_clean["macro_sector"] = [label if macro_sectors_dict[label] > threshold else "other" for label in df["macro_sector"]]
    # remove also subject if macro sector is other
    df_clean.loc[df_clean["macro_sector"] == "other", "subject"] = "other"
    # remove subject is subject count is lesser than min
    df_clean["subject"] = [label if subjects_dict.get(label, 0) > threshold else "other" for label in df_clean["subject"]]
    fig = px.sunburst(df_clean, 
                       path=["macro_sector", "subject"], 
                       values="count", 
                       title=f"Subjects Distribution, {start_year}-{end_year}",
                       color="macro_sector",
                       color_discrete_map=color_map
            )
    fig = apply_global_patterns(fig, pattern_map)
    #fig2.show()  # opens in browser
    filename = f"{OUT_DIR}/{param}_{start_year}-{end_year}"
    df_clean.to_csv(f"{filename}.csv", index=False, encoding="utf-8")
    fig.write_image(f"{filename}.png")

    return fig, filename

def plot_simple_subject_chart(df, param, threshold=0, start_year=None, end_year=None):
    df = df[df["year"].between(start_year, end_year)].copy()
    df["macro_sector"] = df["subject"].str.split("-").str[0]

    counts = df.groupby("macro_sector", as_index=False)["count"].sum()

    # lump sectors at or below the threshold into "other"
    counts.loc[counts["count"] <= threshold, "macro_sector"] = "other"
    counts = counts.groupby("macro_sector", as_index=False)["count"].sum()

    fig = px.pie(
        counts,
        names="macro_sector",
        values="count",
        title=f"Macro Sectors Distribution, {start_year}-{end_year}",
    )

    filename = f"{OUT_DIR}/simple_{param}_{start_year}-{end_year}"
    counts[["macro_sector", "count"]].to_csv(f"{filename}.csv", index=False, encoding="utf-8")
    fig.write_image(f"{filename}.png")
    return fig, filename

def plot_size_histogram(df, min_year=None, max_year=None, param="total_filesize", x_axis="year"):
    if min_year and max_year:
        df_filtered = df[(df["year"] >= min_year) & (df["year"] <= max_year)]
    else:
        df_filtered = df
    if param == "total_filesize":
        div = 3
        unit = "GB"
    else:
        div = 2
        unit = "MB"
    df_filtered[param] = df_filtered[param] / (1024 ** div)
    fig = px.histogram(
        df_filtered,
        x=df_filtered[x_axis].astype(str),
        y=param,
        title=f"{param} by Year ({unit}, log scale)",
        log_y=True,
        color_discrete_sequence=["#AB63FA"],
        pattern_shape_sequence=["x"],
        text_auto=".1f"
    )
    fig.update_yaxes(
        title_text="",        # remove y axis label
        tickmode="array",
        tickvals=[.001, .01, .1, 1, 10, 100, 1000, 10000]
    )
    filename = f"{OUT_DIR}/{param}_{min_year}-{max_year}"
    df_filtered.to_csv(f"{filename}.csv", index=False, encoding="utf-8")
    fig.write_image(f"{filename}.png")
    return fig, filename

def plot_group_sizes(df, start_years=[2015, 2020, 2023, 2026], param="total_filesize"):
    bins = sorted(start_years)
    labels = [f"{s}-{e - 1}" for s, e in zip(bins[:-1], bins[1:])]
    df_filtered = df[(df["year"] >= bins[0]) & (df["year"] < bins[-1])].copy()
    df_filtered[param] = df_filtered[param] / (1024 ** 3)  # bytes -> GB

    df_filtered["year_range"] = pd.cut(    # labels the rows according to the bin values, excluding the right value
        df_filtered["year"], bins=bins, labels=labels, right=False
    )

    df_grouped = (  # groups the values by year_range
        df_filtered
        .groupby("year_range", observed=False, as_index=False)[param]
        .sum()
    )

    fig = px.bar(
        df_grouped,
        x="year_range",
        y=param,
        title=f"{param} by Year Range (GB, log scale)",
        log_y=True,
        color_discrete_sequence=["#AB63FA"],
        pattern_shape_sequence=["x"],
        text_auto=".1f"
    )
    fig.update_xaxes(title_text="")
    fig.update_yaxes(
        title_text="",
        tickmode="array",
        tickvals=[.001, .01, .1, 1, 10, 100, 1000, 10000],
    )

    filename = f"{param}_"
    for label in labels:
        filename += label + "_"

    filename = f"{OUT_DIR}/{filename}"
    df_grouped.to_csv(f"{filename}.csv", index=False, encoding="utf-8")
    fig.write_image(f"{filename}.png")
    return fig, filename

def plot_histogram(df, min_year=0, 
                   max_year=9999, 
                   type_filter=None, 
                   filename="documents", 
                   collapse_all=True,
                   color_map=None,
                   pattern_map=None,
                   plot_order=[None],
                   add_labels=False):
    df_filtered = df[(df["year"] >= min_year) & (df["year"] <= max_year)]
    filter_string = ""
    if type_filter:
        if isinstance(type_filter, str):
            type_filter = [type_filter]
        for filter in type_filter:
            filter_string += filter + "_"
        df_filtered = df_filtered[df_filtered["type"].isin(type_filter)]
        if collapse_all:
            # relabel every selected type as the first one
            df_filtered["type"] = type_filter[0]
    fig = px.bar(
        df_filtered,
        x=df_filtered["year"].astype(int).astype(str),
        y="count",
        color_discrete_map=color_map,
        pattern_shape_map=pattern_map,
        color="type",
        pattern_shape="type",
        title=f"Documents by Year, {min_year}-{max_year}" + (f" — {type_filter}" if type_filter else ""),
        barmode="stack",
        category_orders={"type": plot_order}
        )

    if add_labels:
        totals = df_filtered.groupby("year")["count"].sum().reset_index().sort_values("year")
        totals["type"] = "total"
        
        fig.add_scatter(
            x=totals["year"].astype(int).astype(str),
            y=totals["count"],
            text=totals["count"],
            mode="text",
            textposition="top center",
            showlegend=False
        )
    
    filename = f"{OUT_DIR}/{filename}_{min_year}-{max_year}" + (f"_{filter_string}" if filter_string else "")
    df_filtered.to_csv(f"{filename}.csv", index=False, encoding="utf-8")
    fig.write_image(f"{filename}.png")
    return fig, filename

def plot_grouped_histogram(df, 
                           bins=[2015, 2020, 2023, 2026],
                           type_filter=None,
                           filename="documents",
                           collapse_all=True,
                           color_map=None,
                           pattern_map=None,
                           add_labels=False):
    labels = [f"{s}-{e - 1}" for s, e in zip(bins[:-1], bins[1:])]
    df_filtered = df[(df["year"] >= bins[0]) & (df["year"] < bins[-1])].copy()
    df_filtered["year_range"] = pd.cut(
        df_filtered["year"], bins=bins, labels=labels, right=False
    )

    df_grouped = (
        df_filtered
        .groupby(["year_range", "type"], observed=True, as_index=False)["count"]
        .sum()
    )
    filter_string = ""
    if type_filter:
        if isinstance(type_filter, str):
            type_filter = [type_filter]
        for filter in type_filter:
            filter_string += filter + "_"
        df_grouped = df_grouped[df_grouped["type"].isin(type_filter)]
        if collapse_all:
            # relabel every selected type as the first one
            df_grouped["type"] = type_filter[0]
    
    fig = px.bar(
            df_grouped,
            x=df_grouped["year_range"].astype(str),
            y="count",
            color="type",
            pattern_shape="type",
            color_discrete_map=color_map,
            pattern_shape_map=pattern_map,
            title=f"Documents by Year" + (f" — {type_filter}" if type_filter else ""),
            barmode="stack"
            )
    if add_labels:
        # calculate totals per year
        totals = df_grouped.groupby("year_range")["count"].sum().reset_index().sort_values("year_range")
        totals["type"] = "total"
        fig.add_scatter(
                x=totals["year_range"].astype(str),
                y=totals["count"],
                text=totals["count"],
                mode="text",
                textposition="top center",
                showlegend=False
            )

    for label in labels:
        filename += "_" + label
    filename += (f"_{filter_string}" if filter_string else "")

    filename = f"{OUT_DIR}/{filename}"
    df_grouped.to_csv(f"{filename}.csv", index=False, encoding="utf-8")
    fig.write_image(f"{filename}.png")
    return fig, filename


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
        title=f"Funding information ({param}), {min_year}-{max_year}",
        color=param,
        color_discrete_map={"None": "grey"}
    )
    filename = f"{OUT_DIR}/{param}_{min_year}-{max_year}"
    df_grouped.to_csv(f"{filename}.csv", index=False, encoding="utf-8")
    fig.write_image(f"{filename}.png")
    return fig, filename

def plot_structures(df, param, min_year="", max_year="", threshold=1, df_map=None, color_scheme=None, pattern_scheme=None):
    df_filtered = df[(df["year"] >= min_year) & (df["year"] <= max_year)]
    df_filtered[param] = df.apply(
        lambda r: r[param] if r["count"] > threshold else "Other", axis=1
    )
    # merge all Other rows into one
    df_grouped = df_filtered.groupby(param)["count"].sum().reset_index()
    if df_map is not None:
        df_grouped = (df_grouped.merge(df_map, left_on="structure", right_on="subjectid", how="left")
                      .drop(columns=["subjectid", "structure"])
                      .rename(columns={"name": param}))
        df_grouped["structure"] = df_grouped["structure"].str.split(" - ").str[-1]
    fig = px.treemap(
        df_grouped,
        path=[param],
        values="count",
        title=f"Structures, {min_year}-{max_year}",
        color=param,
        color_discrete_map=color_scheme
    )
    fig = apply_global_patterns(fig, pattern_scheme)
    filename = f"{OUT_DIR}/{param}_{min_year}-{max_year}"
    df_grouped.to_csv(f"{filename}.csv", index=False, encoding="utf-8")
    fig.write_image(f"{filename}.png")
    return fig, filename

def plot_creators(df, min_year="", max_year="", top_n=100):
     # combine family and given into one label
    df["creator"] = df["given"] + " " + df["family"]

    df_grouped = df.groupby("creator")["count"].sum().reset_index()
    df_grouped = df_grouped.nlargest(top_n, "count")

    fig = px.treemap(
        df_grouped,
        path=["creator"],
        values="count",
        title=f"Top {top_n} creators, {min_year}-{max_year}"
    )

    filename = f"{OUT_DIR}/top_{top_n}_creators_{min_year}-{max_year}"
    df_grouped.to_csv(f"{filename}.csv", index=False, encoding="utf-8")
    fig.write_image(f"{filename}.png")
    return fig, filename

def map_subjects_or_structures(collection, type="subjects", df_map=None):
    if type == "types":
        df = get_types(collection)
    else:
        df = get_subjects_or_structures(collection, type)
    
    if type == "subjects":
        df["cat"] = df["subject"].str.split("-").str[0]

    elif df_map is not None:
        df = (df.merge(df_map, left_on="structure", right_on="subjectid", how="left")
                        .drop(columns=["subjectid", "structure"])
            )
        df["name"] = df["name"].str.split(" - ").str[-1]
        df = df.rename(columns={"name": "cat"})
    elif type == "types":
        df = df.rename(columns={"type": "cat"})
    categories = sorted(df["cat"].unique())
    # px.colors.qualitative.Plotly
    # px.colors.qualitative.Set1
    # px.colors.qualitative.Pastel
    # px.colors.qualitative.Dark24   # 24 colors, good for many categories
    # px.colors.qualitative.Light24  # 24 light colors
    colors = cycle(px.colors.qualitative.Plotly)
    shapes = cycle(["/", "\\", ".", "x", "+", "-", "|", ""])
    color_map = {
        cat: next(colors) for cat in categories
    }
    shape_map = {
        cat: next(shapes) for cat in categories
    }
    if type == "subject":
        ssd = sorted(df["subject"].unique())
        ssd_shape_map = {
            cat: shape_map[cat.split(" - ")] for cat in ssd
        }
        shape_map.update(ssd_shape_map)

    return color_map, shape_map

def apply_global_patterns(fig, pattern_scheme):
    """
    Guarantees pattern mapping remains consistent across completely different plots,
    matching categories by name rather than position.
    """
    # Extract Plotly's permanent structural IDs for this specific plot
    ids = fig.data[0].ids
    
    # Safely match categories to your master dictionary
    patterns_list = []
    for sector_id in ids:
        if sector_id == "root" or not sector_id:
            patterns_list.append("")  # Background root gets no pattern
        else:
            category_name = sector_id.split("/")[-1]
            patterns_list.append(pattern_scheme.get(category_name, ""))
            
    # Apply to the figure trace
    fig.update_traces(
        texttemplate="<span style='color: black; text-shadow: -2px -2px 0 #FFF, 2px -2px 0 #FFF, -2px 2px 0 #FFF, 2px 2px 0 #FFF, -2px 0 0 #FFF, 2px 0 0 #FFF, 0 -2px 0 #FFF, 0 2px 0 #FFF;'>%{label}</span>",
        #textposition="middle center",
        marker=dict(
            pattern=dict(
                shape=patterns_list,
                solidity=0.1,         # Subtle opacity so it doesn't overpower the colors
                fgcolor="black",       # Forces pattern lines to be black
                fillmode="overlay"     # FIX: Preserves the solid background color map
            )
        )
    )
    return fig

if __name__ == "__main__":

    #SUBJECTS_MAP = map_subjects_or_structures(collection, "subjects")
        
    start_years = [2015, 2020, 2023]

    subjects_and_structures = pd.read_csv("subject_structure_map.csv", sep=";", quotechar='"', encoding="utf-8")
    
    collection = connect_to_db("mongodb://localhost:27017/",  "admin", "amsacta_documenti")
    STRUCTURES_COLOR_MAP, STRUCTURES_PATTERN_MAP = map_subjects_or_structures(collection, type="structures", df_map=subjects_and_structures)

    types = get_types(collection)

    TYPES_COLOR_MAP, TYPES_PATTERN_MAP = map_subjects_or_structures(collection, type="types")
    
    types_plot, types_filename = plot_histogram(types, 2015, 2025, color_map=TYPES_COLOR_MAP, pattern_map=TYPES_PATTERN_MAP)
    grouped_types_plot, grouped_types_filename = plot_grouped_histogram(df=types,
                                                                        color_map=TYPES_COLOR_MAP,
                                                                        pattern_map=TYPES_PATTERN_MAP)
    datasets_plot, datasets_filename = plot_histogram(types, 2015, 2025, 
                                                      type_filter=["dataset", "software"],
                                                      collapse_all=True,
                                                      color_map=TYPES_COLOR_MAP,
                                                      pattern_map=TYPES_PATTERN_MAP)
    grouped_datasets_plot, grouped_datasets_filename = plot_grouped_histogram(df=types,
                                                                              type_filter=["dataset", "software"],
                                                                              collapse_all=True,
                                                                              color_map=TYPES_COLOR_MAP,
                                                                              pattern_map=TYPES_PATTERN_MAP)
    sizes = get_filesize(collection)
    sizes_plot, sizes_filename = plot_size_histogram(sizes, min_year=2015, max_year=2025)
    grouped_sizes_plot, grouped_sizes_filename = plot_group_sizes(df=sizes)
    sizes_per_record = get_filesizes_per_dataset(collection)
    size_per_record_plot, size_per_record_filename = plot_size_histogram(sizes_per_record, 
                                                                         min_year=2015,
                                                                         max_year=2025,
                                                                         param="median_dataset_size")
    grouped_median_sizes = get_grouped_median_sizes(collection)
    grouped_median_sizes_plot, grouped_median_sizes_filename = plot_size_histogram(df=grouped_median_sizes,
                                                                                   param="median_dataset_size",
                                                                                   x_axis="year_range")
    related = get_related_id(collection)
    related = related.rename(columns={"has_relatedid": "type"})
    related["type"] = related["type"].map({True: "has relatedid", False: "no relatedid"})
    RELATED_COLOR_MAP ={
        "has relatedid": "#AB63FA",
        "no relatedid": "#AB63FA"
    }
    RELATED_PATTERN_MAP ={
            "has relatedid": "/",
            "no relatedid": ""
        }
    related_plot, related_filename = plot_histogram(related,
                                                    min_year=2017,
                                                    max_year=2025,
                                                    filename="relatedid",
                                                    color_map=RELATED_COLOR_MAP,
                                                    pattern_map=RELATED_PATTERN_MAP,
                                                    plot_order=["has relatedid", "no relatedid"])
    grouped_related_plot, grouped_related_filename = plot_grouped_histogram(df=related,
                                                                            filename="relatedid",
                                                                            color_map=RELATED_COLOR_MAP,
                                                                            pattern_map=RELATED_PATTERN_MAP)

    with open("dashboard.html", "w") as f, open("report.md", "w") as r:
    #     f.write("""
    #             <html>
    #             <head>
    #             <style>
    #                 body {
    #                     font-family: Arial, sans-serif;
    #                     margin: 40px;
    #                     background-color: #f9f9f9;
    #                 }
    #                 h1 {
    #                     font-size: 2em;
    #                     color: #333;
    #                     border-bottom: 2px solid #ccc;
    #                     padding-bottom: 10px;
    #                     margin-top: 40px;
    #                 }
    #                 h2 {
    #                     font-size: 1.5em;
    #                     color: #555;
    #                     margin-top: 30px;
    #                 }
    #             </style>
    #             </head>
    #             <body>
    #             """)

        r.write("# Report AMS Acta\n")

    #     f.write("<h1>Documenti per tipologia</h1>")
        r.write("\n## Documenti per tipologia\n")
    #     f.write(types_plot.to_html(full_html=False, include_plotlyjs="cdn"))
    #     f.write("Scarica il file CSV: <a href='" + types_filename + ".csv' download>Download CSV</a><br>")
        r.write(f"\n![Documenti per tipologia]({types_filename}.png)\n\nScarica il file CSV: [{types_filename}.csv]({types_filename}.csv)\n")
    #     f.write(grouped_types_plot.to_html(full_html=False, include_plotlyjs="cdn"))
    #     f.write("Scarica il file CSV: <a href='" + grouped_types_filename + ".csv' download>Download CSV</a><br>")
        r.write(f"\n![Documenti per tipologia]({grouped_types_filename}.png)\n\nScarica il file CSV: [{grouped_types_filename}.csv]({grouped_types_filename}.csv)\n")
    #     f.write(datasets_plot.to_html(full_html=False, include_plotlyjs=False))
    #     f.write("Scarica il file CSV: <a href='" + datasets_filename + ".csv' download>Download CSV</a><br>")
        r.write(f"\n![Documenti per tipologia]({datasets_filename}.png)\n\nScarica il file CSV: [{datasets_filename}.csv]({datasets_filename}.csv)\n")
    #     f.write(grouped_datasets_plot.to_html(full_html=False, include_plotlyjs=False))
    #     f.write("Scarica il file CSV: <a href='" + grouped_datasets_filename + ".csv' download>Download CSV</a><br>")
        r.write(f"\n![Documenti per tipologia]({grouped_datasets_filename}.png)\n\nScarica il file CSV: [{grouped_datasets_filename}.csv]({grouped_datasets_filename}.csv)\n")
    #     f.write("<h1>Dataset con collegamento a pubblicazione</h1>")
        r.write("\n## Dataset con collegamento a pubblicazione\n")
    #     f.write(related_plot.to_html(full_html=False, include_plotlyjs=False))
    #     f.write("Scarica il file CSV: <a href='" + related_filename + ".csv' download>Download CSV</a><br>")
        r.write(f"\n![Dataset con collegamento a pubblicazione]({related_filename}.png)\n\nScarica il file CSV: [{related_filename}.csv]({related_filename}.csv)\n")
    #     f.write(grouped_related_plot.to_html(full_html=False, include_plotlyjs=False))
    #     f.write("Scarica il file CSV: <a href='" + grouped_related_filename + ".csv' download>Download CSV</a><br>")
        r.write(f"\n![Dataset con collegamento a pubblicazione]({grouped_related_filename}.png)\n\nScarica il file CSV: [{grouped_related_filename}.csv]({grouped_related_filename}.csv)\n")
    #     f.write("<h1>Volume dei dataset</h1>")
        r.write("\n## Volume dei dataset\n")
    #     f.write(sizes_plot.to_html(full_html=False, include_plotlyjs=False))
    #     f.write("Scarica il file CSV: <a href='" + sizes_filename + ".csv' download>Download CSV</a><br>")
        r.write(f"\n![Volume dei dataset]({sizes_filename}.png)\n\nScarica il file CSV: [{sizes_filename}.csv]({sizes_filename}.csv)\n")
    #     f.write(grouped_sizes_plot.to_html(full_html=False, include_plotlyjs=False))
    #     f.write("Scarica il file CSV: <a href='" + grouped_sizes_filename + ".csv' download>Download CSV</a><br>")
        r.write(f"\n![Volume dei dataset]({grouped_sizes_filename}.png)\n\nScarica il file CSV: [{grouped_sizes_filename}.csv]({grouped_sizes_filename}.csv)\n")

        r.write(f"\n![Volume dei dataset]({size_per_record_filename}.png)\n\nScarica il file CSV: [{size_per_record_filename}.csv]({size_per_record_filename}.csv)\n")

        r.write(f"\n![Volume dei dataset]({grouped_median_sizes_filename}.png)\n\nScarica il file CSV: [{grouped_median_sizes_filename}.csv]({grouped_median_sizes_filename}.csv)\n")

        

    #     f.write("<h1>Settori disciplinari (dataset e software)</h1>")
        r.write("\n## Settori disciplinari\n")
        SUBJECTS_COLOR_MAP, SUBJECTS_PATTERN_MAP = map_subjects_or_structures(collection, type="subjects", df_map=subjects_and_structures)
        for start_year in start_years:
            end_year = start_year + 2 if start_year > 2015 else start_year + 4
            subjects = get_subjects_or_structures(collection)
            threshold = 5 if start_year > 2019 else 1
            subjects_plot, subjects_filename = plot_subject_chart(df=subjects,
                                                                  param="subject",
                                                                  threshold=threshold,
                                                                  start_year=start_year,
                                                                  end_year=end_year,
                                                                  color_map=SUBJECTS_COLOR_MAP,
                                                                  pattern_map=SUBJECTS_PATTERN_MAP)
            simple_subjects_plot, simple_subjects_filename = plot_simple_subject_chart(df=subjects, param="subject", threshold=threshold, start_year=start_year, end_year=end_year)
    #         f.write(subjects_plot.to_html(full_html=False, include_plotlyjs=False))
    #         f.write("Scarica il file CSV: <a href='" + subjects_filename + ".csv' download>Download CSV</a><br>")
    #         f.write(simple_subjects_plot.to_html(full_html=False, include_plotlyjs=False))
    #         f.write("Scarica il file CSV: <a href='" + simple_subjects_filename + ".csv' download>Download CSV</a><br>")
            r.write(f"\n![Settori disciplinari]({subjects_filename}.png)\n\nScarica il file CSV: [{subjects_filename}.csv]({subjects_filename}.csv)\n")
    #        r.write(f"\n![Settori disciplinari (semplice)]({simple_subjects_filename}.png)\n\nScarica il file CSV: [{simple_subjects_filename}.csv]({simple_subjects_filename}.csv)\n")

    #     f.write("<h1>Strutture (dataset e software)</h1>")
        r.write("\n## Strutture\n")
        for start_year in start_years:
            end_year = start_year + 2 if start_year > 2015 else start_year + 4
            structures = get_subjects_or_structures(collection, type="structures")
            structures_plot, structures_filename = plot_structures(df=structures, 
                                              param="structure", 
                                              threshold=0, 
                                              min_year=start_year, 
                                              max_year=end_year,
                                              df_map=subjects_and_structures,
                                              color_scheme=STRUCTURES_COLOR_MAP,
                                              pattern_scheme=STRUCTURES_PATTERN_MAP)
    #        f.write(structures_plot.to_html(full_html=False, include_plotlyjs=False))
    #        f.write("Scarica il file CSV: <a href='" + structures_filename + ".csv' download>Download CSV</a><br>")
            r.write(f"\n![Strutture]({structures_filename}.png)\n\nScarica il file CSV: [{structures_filename}.csv]({structures_filename}.csv)\n")

    #     f.write("<h1>Progetti (dataset e software)</h1>")
        r.write("\n## Progetti\n")
    #     for start_year in start_years:
    #         param = "projectacronym"
    #         end_year = start_year + 2 if start_year > 2015 else start_year + 4
    #         projects = get_funding_info(collection, param, start_year, end_year, get_all=True)
    #         projects_plot, projects_filename = plot_funding_treemap(projects, param, start_year, end_year)
    #         f.write(projects_plot.to_html(full_html=False, include_plotlyjs=False))
    #         f.write("Scarica il file CSV: <a href='" + projects_filename + ".csv' download>Download CSV</a><br>")
    #         r.write(f"\n![Progetti]({projects_filename}.png)\n\nScarica il file CSV: [{projects_filename}.csv]({projects_filename}.csv)\n")

    #     f.write("<h1>Enti finanziatori (dataset e software)</h1>")
    #     r.write("\n## Enti finanziatori\n")
    #     for start_year in start_years:
    #         end_year = start_year + 2 if start_year > 2015 else start_year + 4
    #         funders = get_funding_info(collection, "funder", start_year, end_year, get_all=True)
    #         funders_plot, funders_filename = plot_funding_treemap(funders, "funder", start_year, end_year)
    #         f.write(funders_plot.to_html(full_html=False, include_plotlyjs=False))
    #         f.write("Scarica il file CSV: <a href='" + funders_filename + ".csv' download>Download CSV</a><br>")
    #         r.write(f"\n![Enti finanziatori]({funders_filename}.png)\n\nScarica il file CSV: [{funders_filename}.csv]({funders_filename}.csv)\n")

    #     f.write("<h1>Creatori (dataset e software)</h1>")
    #     r.write("\n## Creatori\n")
    #     for start_year in start_years:
    #         top_n = 50
    #         end_year = start_year + 2 if start_year > 2015 else start_year + 4
    #         creators = get_creators(collection, start_year, end_year)
    #         creators_plot, filename = plot_creators(creators, start_year, end_year, top_n=top_n)
    #         f.write(creators_plot.to_html(full_html=False, include_plotlyjs=False))
    #         f.write("Scarica il file CSV: <a href='" + filename + ".csv' download>Download CSV</a><br>")
    #         r.write(f"\n![Creatori]({filename}.png)\n\nScarica il file CSV: [{filename}.csv]({filename}.csv)\n")

    #     f.write("</body></html>")
