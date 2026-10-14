from pymongo import MongoClient
import os
import pandas as pd
import matplotlib.pyplot as plt
import plotly.express as px
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import plotly.io as pio
from itertools import cycle

OUT_DIR = "out"
CSV_DIR = "csv"
PNG_DIR = "png"
SVG_DIR = "svg"
PNG_PATH = f"{OUT_DIR}/{PNG_DIR}"
SVG_PATH = f"{OUT_DIR}/{SVG_DIR}"
CSV_PATH = f"{OUT_DIR}/{CSV_DIR}"
DEFAULT_SCALE = 2
CACHE_DIR = "queries"
USE_CACHED_IMG = False
SAVE_SVG = True
SAVE_PNG = True

figures = []

def connect_to_db(client_url, db_name, collection_name):
    print("Connecting to MongoDB...")
    client = MongoClient()  # or your Atlas connection string
    db = client["admin"]
    collection = db["amsacta_documenti"]
    return collection

def get_subjects_or_structures(collection, type="subjects"):
    singular = type[:-1]
    if os.path.exists(f"{CACHE_DIR}/{type}.csv"):
        print(f"Loading cached {type} data...")
        df = pd.read_csv(f"{CACHE_DIR}/{type}.csv", 
                         encoding="utf-8",
                         dtype={
                             "year": int,
                             "count": int,
                             singular: str
                         })
        return df
    else:
        print(f"Querying {type} data from MongoDB...")
        pipeline = [
            {
                "$match": {
                     "type": { "$in": ["dataset", "software"] },
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
                        singular: { "$toString": f"${type}" }
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
        df.to_csv(f"{CACHE_DIR}/{type}.csv", index=False, encoding="utf-8")
        return df

def get_types(collection, collapse_types=False):
    if os.path.exists(f"{CACHE_DIR}/types.csv"):
        print("Loading cached types data...")
        df = pd.read_csv(f"{CACHE_DIR}/types.csv", encoding="utf-8")
        return df
    else:
        print("Querying types data from MongoDB...")
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

        if collapse_types:
            pipeline.insert(1, {
                "$addFields": {
                    "type": {
                        "$switch": {
                            "branches": [
                                { "case": { "$in": ["$type", ["software", "dataset"]] }, "then": "dataset/software" },
                                { "case": { "$in": ["$type", ["preprint", "working_paper"]] }, "then": "preprint/working paper" }
                            ],
                            "default": "$type"
                        }
                    }
                }
            },)

        results = list(collection.aggregate(pipeline))
        df = pd.json_normalize(results).rename(columns={
            "_id.year": "year",
            "_id.type": "type"
        })
        df.to_csv(f"{CACHE_DIR}/types.csv", index=False, encoding="utf-8")

        return df

def get_filesize(collection):
    if os.path.exists(f"{CACHE_DIR}/filesizes.csv"):
        print("Loading cached filesizes data...")
        df = pd.read_csv(f"{CACHE_DIR}/filesizes.csv", encoding="utf-8")
        return df
    else:
        print("Querying filesizes data from MongoDB...")
        pipeline = [
            {
                "$match": {
                    "type": { "$in": ["dataset", "software"] },
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
        df.to_csv(f"{CACHE_DIR}/filesizes.csv", index=False, encoding="utf-8")
        return df

def get_filesizes_per_dataset(collection):
    if os.path.exists(f"{CACHE_DIR}/median_dataset_sizes.csv"):
        print("Loading cached median dataset sizes data...")
        df = pd.read_csv(f"{CACHE_DIR}/median_dataset_sizes.csv", encoding="utf-8")
        return df
    else:
        print("Querying median dataset sizes data from MongoDB...")
        pipeline = [
        {
                "$match": {
                    "type": { "$in": ["dataset", "software"] },
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
        df.to_csv(f"{CACHE_DIR}/median_dataset_sizes.csv", index=False, encoding="utf-8")

        pipeline_check2 = [
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
                "$group": {
                    "_id": "$_id.year",
                    "median": { "$median": { "input": "$total_filesize", "method": "approximate" } },
                    "avg": { "$avg": "$total_filesize" },
                    "min": { "$min": "$total_filesize" },
                    "max": { "$max": "$total_filesize" },
                    "count": { "$sum": 1 }
                }
            },
            { "$sort": { "_id": 1 } }
        ]

        print(list(collection.aggregate(pipeline_check2)))

        return df

def get_grouped_median_sizes(collection, bins=None):
    if bins is None:
        bins = [2016, 2020, 2023, 2026]
    range_labels = [f"{bins[i]}-{bins[i+1]}" for i in range(len(bins)-1)]
    years = "_".join(range_labels)
    if os.path.exists(f"{CACHE_DIR}/median_dataset_sizes_{years}.csv"):
        print(f"Loading cached grouped median dataset sizes data for {years}...")
        df = pd.read_csv(f"{CACHE_DIR}/median_dataset_sizes_{years}.csv", encoding="utf-8")
        return df
    else:
        print(f"Querying grouped median dataset sizes data for {years}...")
        branches = []
        for i in range(len(bins) - 1):
            branches.append({
                "case": { "$and": [
                    { "$gte": ["$_id.year", bins[i]] },
                    { "$lt": ["$_id.year", bins[i+1]] }
                ]},
                "then": range_labels[i]  # ← use same label
            })

        pipeline = [
            {
                "$match": {
                    "type": { "$in": ["dataset", "software"] },
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
                            "default": "$REMOVE"
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
        df.to_csv(f"{CACHE_DIR}/median_dataset_sizes_{years}.csv", index=False, encoding="utf-8")
        return df

def get_funding_info(collection, param, start_year, end_year, get_all=False):
    if os.path.exists(f"{CACHE_DIR}/{param}_funding_info_{start_year}_{end_year}.csv"):
        print(f"Loading cached funding info data for {param}, {start_year}-{end_year}...")
        df = pd.read_csv(f"{CACHE_DIR}/{param}_funding_info_{start_year}_{end_year}.csv", encoding="utf-8")
        return df
    else:
        print(f"Querying funding info data for {param}, {start_year}-{end_year}...")
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
                        "type": { "$in": ["dataset", "software"] }
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
                        "fundingprogramme": 1,
                        "_id": 0
                    }
                },
                {
                    "$group": {
                        "_id": {
                            "param": f"${param}",
                            "fundingprogramme": "$fundingprogramme",
                        },
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
                    "type": { "$in": ["dataset", "software"] },
                    param: { "$exists": True, "$ne": None }
                }
            },
            {
                "$project": { 
                    param: 1,
                    "fundingprogramme": 1,
                    "_id": 0
                }
            },
            {
                "$group": {
                    "_id": {
                        "param": f"${param}",
                        "fundingprogramme": "$fundingprogramme",
                    },
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
        df = pd.json_normalize(results).rename(columns={"_id.param": param, "_id.fundingprogramme": "fundingprogramme"})
        df.to_csv(f"{CACHE_DIR}/{param}_funding_info_{start_year}_{end_year}.csv", index=False, encoding="utf-8")
        return df

def get_creators(collection, start_year, end_year):
    if os.path.exists(f"{CACHE_DIR}/creators_{start_year}_{end_year}.csv"):
        print(f"Loading cached creators data for {start_year}-{end_year}...")
        df = pd.read_csv(f"{CACHE_DIR}/creators_{start_year}_{end_year}.csv", encoding="utf-8")
        return df
    else:
        print(f"Querying creators data for {start_year}-{end_year}...")
        start_date=f"{start_year}-01-01"
        end_date=f"{end_year+1}-01-01"
        pipeline = [
            {
                "$match": {
                    "datestamp": {
                        "$gt": start_date,
                        "$lt": end_date
                    },
                    "type": { "$in": ["dataset", "software"] },
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
        df.to_csv(f"{CACHE_DIR}/creators_{start_year}_{end_year}.csv", index=False, encoding="utf-8")
        return df

def get_related_id(collection):
    if os.path.exists(f"{CACHE_DIR}/related_ids.csv"):
        print("Loading cached related IDs data...")
        df = pd.read_csv(f"{CACHE_DIR}/related_ids.csv", encoding="utf-8")
        return df
    else:
        print("Querying related IDs data from MongoDB...")
        pipeline = [
            {
                "$match": {
                    "type": { "$in": ["dataset", "software"] },
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
        df.to_csv(f"{CACHE_DIR}/related_ids.csv", index=False, encoding="utf-8")
        return df

def save_figure(fig, filename, scale=DEFAULT_SCALE, png=SAVE_PNG, svg=SAVE_SVG, use_cached=USE_CACHED_IMG):
    if use_cached:
        return True
    if png:
        print(f"Saving figure {filename} in PNG format...")
        fig.write_image(f"{OUT_DIR}/{PNG_DIR}/{filename}.png", scale=scale)
    if svg:
        print(f"Saving figure {filename} in SVG format...")
        fig.write_image(f"{OUT_DIR}/{SVG_DIR}/{filename}.svg")

def save_all_figures(figures_dict, scale=DEFAULT_SCALE, png=SAVE_PNG, svg=SAVE_SVG, use_cached=USE_CACHED_IMG):
    for figure in figures_dict:
        save_figure(figure["fig"], figure["filename"], scale=scale, png=png, svg=svg, use_cached=use_cached)

def plot_subject_chart(df, param, 
                       threshold=0, 
                       start_year=None, 
                       end_year=None, 
                       color_map=None, 
                       pattern_map=None):
    print(f"Plotting subject chart for {param}, {start_year}-{end_year}...")
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
    title=f"Subjects distribution, {start_year}-{end_year} (threshold: {threshold})"
    fig = px.sunburst(df_clean, 
                       path=["macro_sector", "subject"], 
                       values="count",
                       color="macro_sector",
                       color_discrete_map=color_map
            )
    fig = apply_global_patterns(fig, pattern_map)
    #fig2.show()  # opens in browser
    filename = f"{param}_{start_year}-{end_year}"
    df_clean.to_csv(f"{OUT_DIR}/{CSV_DIR}/{filename}.csv", index=False, encoding="utf-8")
    #save_figure(fig, filename)
    figures.append({
                    "filename": filename,
                    "fig": fig,
                    "title": title
                })
    return fig, filename

def plot_pie_chart(df, param, start_year=2016, end_year=2025, threshold=0, color_map=None, pattern_map=None):
    df_filtered = df[df["year"].isin(range(start_year, end_year))]
    df_grouped = df_filtered.groupby(param)["count"].sum().reset_index()
    print(f"Plotting simple subject chart for {param}...")
    title=f"{param} distribution, {start_year}-{end_year}"
    fig = px.pie(
        df_grouped,
        names=param,
        values="count",
        color=param,
        color_discrete_map=color_map
    )
    
    fig.update_traces(
        textposition="outside",
        textinfo="percent",
        texttemplate="%{percent:.1%}",
        marker=dict(
            pattern=dict(
                shape=[pattern_map[cat] for cat in df_grouped[param]],
                solidity=0.1,
                fgcolor="black",  # pattern color
                bgcolor=[color_map[cat] for cat in df_grouped[param]]  # background color
            )
        )
    )

    filename = f"pie_{param}_{start_year}-{end_year}"
    df.to_csv(f"{OUT_DIR}/{CSV_DIR}/{filename}.csv", index=False, encoding="utf-8")
    figures.append({
        "filename": filename,
        "fig": fig,
        "title": title
    })
    return fig, filename

def plot_simple_subject_chart(df, param, threshold=0, start_year=None, end_year=None):
    print(f"Plotting simple subject chart for {param}, {start_year}-{end_year}...")
    df = df[df["year"].between(start_year, end_year)].copy()
    df["macro_sector"] = df["subject"].str.split("-").str[0]

    counts = df.groupby("macro_sector", as_index=False)["count"].sum()

    # lump sectors at or below the threshold into "other"
    counts.loc[counts["count"] <= threshold, "macro_sector"] = "other"
    counts = counts.groupby("macro_sector", as_index=False)["count"].sum()
    title=f"Macro Sectors Distribution, {start_year}-{end_year}"
    fig = px.pie(
        counts,
        names="macro_sector",
        values="count"
    )

    filename = f"simple_{param}_{start_year}-{end_year}"
    counts[["macro_sector", "count"]].to_csv(f"{OUT_DIR}/{CSV_DIR}/{filename}.csv", index=False, encoding="utf-8")
    #save_figure(fig, filename)
    figures.append({
            "filename": filename,
            "fig": fig,
            "title": title
        })
    return fig, filename

def plot_size_histogram(df, min_year=None, 
                        max_year=None, 
                        param="total_filesize", 
                        x_axis="year", 
                        log_scale=True):
    print(f"Plotting size histogram for {param}, {min_year}-{max_year}...")
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
    title=f"{param} by {x_axis} ({unit})" + (", log scale" if log_scale else "")
    fig = px.histogram(
        df_filtered,
        x=df_filtered[x_axis].astype(str),
        y=param,
        log_y=log_scale,
        color_discrete_sequence=["#AB63FA"],
        pattern_shape_sequence=["x"],
        text_auto=".1f"
    )

    if log_scale:
        fig.update_yaxes(
            title_text="",        # remove y axis label
            tickmode="array",
            tickvals=[.001, .01, .1, 1, 10, 100, 1000, 10000]
        )
    else:
        fig.update_yaxes(title_text=None)

    fig.update_xaxes(title_text=None)
    fig.update_layout(legend=dict(
                        orientation="h",
                        yanchor="top",
                        y=-.15,
                        xanchor="right",
                        x=1
                    ))
       
    filename = f"{param}_{min_year}-{max_year}"
    df_filtered.to_csv(f"{OUT_DIR}/{CSV_DIR}/{filename}.csv", index=False, encoding="utf-8")
    #save_figure(fig, filename)
    figures.append({
                "filename": filename,
                "fig": fig,
                "title": title
            })
    return fig, filename

def plot_group_sizes(df, start_years=[2016, 2020, 2023, 2026], param="total_filesize"):
    bins = sorted(start_years)
    labels = [f"{s}-{e - 1}" for s, e in zip(bins[:-1], bins[1:])]
    label_string = ", ".join(labels)
    print(f"Plotting grouped sizes for {labels}...")
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

    title=f"{param} by year range, {label_string} (GB, log scale)"

    fig = px.bar(
        df_grouped,
        x="year_range",
        y=param,
        log_y=True,
        color_discrete_sequence=["#AB63FA"],
        pattern_shape_sequence=["x"],
        text_auto=".1f"
    )
    fig.update_xaxes(title_text=None)
    fig.update_yaxes(
        title_text="",
        tickmode="array",
        tickvals=[.001, .01, .1, 1, 10, 100, 1000, 10000],
    )

    filename = f"{param}_"
    for label in labels:
        filename += label + "_"
    df_grouped.to_csv(f"{OUT_DIR}/{CSV_DIR}/{filename}.csv", index=False, encoding="utf-8")
    #save_figure(fig, filename)
    figures.append({
                    "filename": filename,
                    "fig": fig,
                    "title": title
                })
    return fig, filename

def plot_histogram(df, min_year=0, 
                   max_year=9999, 
                   type_filter=None, 
                   filename="documents",
                   param="count",
                   collapse_all=True,
                   color_map=None,
                   pattern_map=None,
                   plot_order=[None],
                   add_labels=False,
                   add_percentage=False):
    
    print(f"Plotting {filename} histogram for {min_year}-{max_year}...")
    df_filtered = df[(df["year"] >= min_year) & (df["year"] <= max_year)]
    filter_string = ""
    type_name = ""
    if type_filter:
        if isinstance(type_filter, str):
            type_filter = [type_filter]
        for filter in type_filter:
            filter_string += filter + "_"
        df_filtered = df_filtered[df_filtered["type"].isin(type_filter)]
        if collapse_all:
            # relabel every selected type as the first one
            type_name = type_filter[0]
            for name in type_filter[1:]:
                type_name += " and " + name
            df_filtered["type"] = type_name
            if color_map:
                color_map[type_name] = color_map.get(type_filter[0])
            if pattern_map:
                pattern_map[type_name] = pattern_map.get(type_filter[0])
    
    title=f"Documents by year, {min_year}-{max_year}" + (f" — {type_name}" if type_name else "")
    
    fig = px.bar(
        df_filtered,
        x=df_filtered["year"].astype(int).astype(str),
        y=param,
        color_discrete_map=color_map,
        pattern_shape_map=pattern_map,
        color="type",
        pattern_shape="type",
        barmode="stack",
        category_orders={"type": plot_order}
        )

    if add_percentage:
        totals_pct = df_filtered.groupby("year")[param].sum().reset_index()
        totals_pct = totals_pct.rename(columns={param: "total"})
        df_filtered = df_filtered.merge(totals_pct, on="year")
        df_filtered["percentage"] = (df_filtered[param] / df_filtered["total"] * 100).round(1)
        
        fig = px.bar(
            df_filtered,
            x=df_filtered["year"].astype(int).astype(str),
            y=param,
            color_discrete_map=color_map,
            pattern_shape_map=pattern_map,
            color="type",
            pattern_shape="type",
            barmode="stack",
            category_orders={"type": plot_order},
            text=df_filtered["percentage"].apply(lambda x: f"{x}%")
        )
        fig.update_traces(textposition="inside", textfont=dict(color="white"))

    if add_labels:
        totals = df_filtered.groupby("year")[param].sum().reset_index().sort_values("year")
        totals["type"] = "total"
        
        fig.add_scatter(
            x=totals["year"].astype(int).astype(str),
            y=totals[param],
            text=totals[param],
            mode="text",
            textposition="top center",
            showlegend=False
        )

    fig.update_xaxes(title_text=None)
    fig.update_yaxes(range=[0, None],
                     title_text=None)

    unique_categories = df_filtered["type"].nunique()

    fig.update_layout(legend=dict(
                    orientation="h",
                    yanchor="top",
                    y=-.15,
                    xanchor="right",
                    x=1
                ),
                showlegend=True if unique_categories > 1 else False
        )
    
    filename = f"{filename}_{min_year}-{max_year}" + (f"_{filter_string}" if filter_string else "")
    filename = filename.replace("/", "-").replace("\\", "-")
    df_filtered.to_csv(f"{OUT_DIR}/{CSV_DIR}/{filename}.csv", index=False, encoding="utf-8")
    #save_figure(fig, filename)
    figures.append({
                    "filename": filename,
                    "fig": fig,
                    "title": title
                })
    return fig, filename

def plot_grouped_histogram(df, 
                           bins=[2016, 2020, 2023, 2026],
                           type_filter=None,
                           param="count",
                           filename="documents",
                           collapse_all=True,
                           color_map=None,
                           pattern_map=None,
                           add_labels=False,
                           add_percentage=False):
    labels = [f"{s}-{e - 1}" for s, e in zip(bins[:-1], bins[1:])]
    label_string = ", ".join(labels)
    print(f"Plotting grouped histogram for {labels}...")
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
    type_name = ""
    if type_filter:
        if isinstance(type_filter, str):
            type_filter = [type_filter]
        for filter in type_filter:
            filter_string += filter + "_"
        df_grouped = df_grouped[df_grouped["type"].isin(type_filter)]
        if collapse_all:
            # relabel every selected type as the first one
            type_name = type_filter[0]
            for name in type_filter[1:]:
                type_name += " and " + name
            df_grouped["type"] = type_name
            if color_map:
                color_map[type_name] = color_map.get(type_filter[0])
            if pattern_map:
                pattern_map[type_name] = pattern_map.get(type_filter[0])

    title=f"Documents by year, {label_string}" + (f" — {type_name}" if type_name else "")
    
    fig = px.bar(
            df_grouped,
            x=df_grouped["year_range"].astype(str),
            y="count",
            color="type",
            pattern_shape="type",
            color_discrete_map=color_map,
            pattern_shape_map=pattern_map,
            barmode="stack"
            )

    if add_percentage:
        totals_pct = df_grouped.groupby("year_range")[param].sum().reset_index()
        totals_pct = totals_pct.rename(columns={param: "total"})
        df_grouped = df_grouped.merge(totals_pct, on="year_range")
        df_grouped["percentage"] = (df_grouped[param] / df_grouped["total"] * 100).round(1)
        
        fig = px.bar(
            df_grouped,
            x=df_grouped["year_range"].astype(str),
            y=param,
            color_discrete_map=color_map,
            pattern_shape_map=pattern_map,
            color="type",
            pattern_shape="type",
            barmode="stack",
            text=df_grouped["percentage"].apply(lambda x: f"{x}%"),
        )
        fig.update_traces(textposition="inside", textfont=dict(color="white"))

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

    fig.update_xaxes(title_text=None)

    unique_categories = df_grouped["type"].nunique()

    fig.update_layout(legend=dict(
                    orientation="h",
                    yanchor="top",
                    y=-.15,
                    xanchor="right",
                    x=1
                ),
                showlegend=True if unique_categories > 1 else False
    )

    for label in labels:
        filename += "_" + label
    filename += (f"_{filter_string}" if filter_string else "")
    filename = filename.replace("/", "-").replace("\\", "-")
    df_grouped.to_csv(f"{OUT_DIR}/{CSV_DIR}/{filename}.csv", index=False, encoding="utf-8")
    #save_figure(fig, filename)
    figures.append({
                        "filename": filename,
                        "fig": fig,
                        "title": title
                    })
    return fig, filename


def plot_funding_treemap(df, param, min_year="", max_year="", threshold=1, color_scheme=None, pattern_scheme=None):
    print(f"Plotting funding treemap for {param}, {min_year}-{max_year}...")
    df[param] = df[param].fillna("None")
    df[param] = df.apply(
        lambda r: r[param] if r["count"] > threshold else "Other", axis=1
    )
    df.loc[df["projectacronym"] == "Other", "fundingprogramme"] = None
    # merge all Other rows into one
    df_grouped = df.fillna("").groupby([param, "fundingprogramme"])["count"].sum().reset_index()
    title=f"Funding information ({param}), {min_year}-{max_year} (threshold = {threshold})"
    fig = px.treemap(
        df_grouped,
        path=[param],
        values="count",
        color=param,
        color_discrete_map=color_scheme
    )
    fig = apply_global_patterns(fig, pattern_scheme, df_grouped, param, "fundingprogramme", add_value=True)
    filename = f"{param}_{min_year}-{max_year}"
    df_grouped.to_csv(f"{OUT_DIR}/{CSV_DIR}/{filename}.csv", index=False, encoding="utf-8")
    #save_figure(fig, filename)
    figures.append({
                    "filename": filename,
                    "fig": fig,
                    "title": title
                })
    return fig, filename

def plot_structures(df, param, min_year="", max_year="", threshold=1, df_map=None, color_scheme=None, pattern_scheme=None):
    print(f"Plotting treemap for {param}, {min_year}-{max_year}...")
    df_filtered = df[(df["year"] >= min_year) & (df["year"] <= max_year)]
    df_filtered = df_filtered.copy()
    df_filtered[param] = df_filtered.apply(
        lambda r: r[param] if r["count"] > threshold else "Other", axis=1
    )
    # merge all Other rows into one
    df_grouped = df_filtered.groupby(param, dropna=False)["count"].sum().reset_index()
    df_grouped["structure"] = df_grouped["structure"].fillna("Other")
    df_grouped = df_grouped[df_grouped[param] != ""]
    if df_map is not None:
        df_grouped = (df_grouped.merge(df_map, left_on="structure", right_on="subjectid", how="left")
                      .drop(columns=["subjectid", "structure"])
                      .rename(columns={"name": param}))
        df_grouped["structure"] = df_grouped["structure"].str.split(" - ").str[-1]
    df_grouped[param] = df_grouped[param].fillna("None")

    title=f"Structures, {min_year}-{max_year} (threshold = {threshold})"

    fig = px.treemap(
        df_grouped,
        path=[param],
        values="count",
        color=param,
        color_discrete_map=color_scheme
    )
    fig = apply_global_patterns(fig, pattern_scheme, add_value=True)
    filename = f"{param}_{min_year}-{max_year}"
    df_grouped.to_csv(f"{OUT_DIR}/{CSV_DIR}/{filename}.csv", index=False, encoding="utf-8")
    #save_figure(fig, filename)
    figures.append({
                    "filename": filename,
                    "fig": fig,
                    "title": title
                })
    return fig, filename

def plot_creators(df, min_year="", max_year="", top_n=100):
    print(f"Plotting top {top_n} creators chart for {min_year}-{max_year}...")
    # combine family and given into one label
    df["creator"] = df["given"] + " " + df["family"]

    df_grouped = df.groupby("creator")["count"].sum().reset_index()
    df_grouped = df_grouped.nlargest(top_n, "count")

    title=f"Top {top_n} creators, {min_year}-{max_year}"

    fig = px.treemap(
        df_grouped,
        path=["creator"],
        values="count",
    )

    filename = f"top_{top_n}_creators_{min_year}-{max_year}"
    df_grouped.to_csv(f"{OUT_DIR}/{CSV_DIR}/{filename}.csv", index=False, encoding="utf-8")
    #save_figure(fig, filename)
    figures.append({
                    "filename": filename,
                    "fig": fig,
                    "title": title
                })
    return fig, filename

def map_subjects_or_structures(collection, type="subjects", df_map=None):
    print(f"Creating color and shape maps for {type}...")
    if type == "types":
        df = get_types(collection)
    if type == "projectacronym":
        df = get_funding_info(collection, param="projectacronym", start_year=2016, end_year=2025, get_all=True)
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
    elif type == "types" or type == "projectacronym":
        if type == "types":
            type = "type"
        else:
            df["projectacronym"] = df["projectacronym"].fillna("None")
        df = df.rename(columns={type: "cat"})
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

    color_map.update({
        "Other": "lightgrey",
        "other": "grey",
        "None": "grey"
    })

    shape_map.update({
        "Other": "/",
        "other": "/",
        "None": "/"
    })

    return color_map, shape_map

def apply_global_patterns(fig, pattern_scheme, df_source=None, param_col=None, custom_data_col=None, add_value=False):
    """
    Guarantees pattern mapping remains consistent across completely different plots,
    matching categories by name rather than position. Handles custom data mapping safely
    for treemaps if source data is provided.
    """
    # 1. Handle customdata mapping ONLY if all source dataframe arguments are passed
    if df_source is not None and param_col is not None and custom_data_col is not None:
        custom_map = dict(zip(df_source[param_col].astype(str), df_source[custom_data_col].astype(str)))
        ids = fig.data[0].ids
        
        aligned_customdata = []
        for sector_id in ids:
            if sector_id == "root" or not sector_id:
                aligned_customdata.append("")
            else:
                category_name = sector_id.split("/")[-1]
                aligned_customdata.append(custom_map.get(category_name, ""))
        
        # Inject customdata array safely into the primary trace
        fig.data[0].customdata = aligned_customdata
        
        # Apply the specific text template that utilizes the new customdata
        text_template = (
            "<span style='color: black; text-shadow: -2px -2px 0 #FFF, 2px -2px 0 #FFF, "
            "-2px 2px 0 #FFF, 2px 2px 0 #FFF, -2px 0 0 #FFF, 2px 0 0 #FFF, 0 -2px 0 #FFF, "
            "0 2px 0 #FFF;'>%{label} (%{value})<br>%{customdata}</span>"
        )
    elif add_value:
        text_template = (
            "<span style='color: black; text-shadow: -2px -2px 0 #FFF, 2px -2px 0 #FFF, "
            "-2px 2px 0 #FFF, 2px 2px 0 #FFF, -2px 0 0 #FFF, 2px 0 0 #FFF, 0 -2px 0 #FFF, "
            "0 2px 0 #FFF;'>%{label} (%{value})</span>"
        )
    else:
        text_template = (
            "<span style='color: black; text-shadow: -2px -2px 0 #FFF, 2px -2px 0 #FFF, "
            "-2px 2px 0 #FFF, 2px 2px 0 #FFF, -2px 0 0 #FFF, 2px 0 0 #FFF, 0 -2px 0 #FFF, "
            "0 2px 0 #FFF;'>%{label}</span>"
        )

    # 2. Extract Plotly's structural IDs for pattern matching (Shared logic)
    ids = fig.data[0].ids
    patterns_list = []
    for sector_id in ids:
        if sector_id == "root" or not sector_id:
            patterns_list.append("")  # Background root gets no pattern
        else:
            category_name = sector_id.split("/")[-1]
            patterns_list.append(pattern_scheme.get(category_name, ""))
            
    # 3. Apply styles universally to the figure trace
    fig.update_traces(
        texttemplate=text_template,

        marker=dict(
            pattern=dict(
                shape=patterns_list,
                solidity=0.1,         # Subtle opacity so it doesn't overpower the colors
                fgcolor="black",       # Forces pattern lines to be black
                fillmode="overlay"     # Preserves the solid background color map
            )
        )
    )
    return fig

def save_md_report(figures_dict, report_filename="report.md"):
    with open(report_filename, "w", encoding="utf-8") as r:
        r.write("# Report AMS Acta\n")
        for figure in figures_dict:
            filename = figure["filename"]
            r.write(f"\n## {figure['title']}\n")
            r.write(f"![{filename}]({SVG_PATH}/{filename}.svg)\n\n")
            r.write(f"Scarica il file CSV: [{filename}.csv]({CSV_PATH}/{filename}.csv)\n")

def save_html_dashboard(figures_dict, dashboard_filename="dashboard.html"):
    print("Writing html dashboard...")
    with open(dashboard_filename, "w") as f:
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
        for figure in figures_dict:
            filename = figure["filename"]
            fig = figure["fig"]
            f.write(f"<h1>{figure['title']}</h1>")
            f.write(fig.to_html(full_html=False, include_plotlyjs="cdn"))
            f.write(f"Scarica il file CSV: <a href='{CSV_PATH}/{filename}.csv' download>Download CSV</a><br>")
            f.write(f"Scarica l'immagine in formato: <a href='{PNG_PATH}/{filename}.png'>PNG</a> | <a href='{SVG_PATH}/{filename}.svg'>SVG</a>")
        f.write("</body></html>")

def create_plots():

    #SUBJECTS_MAP = map_subjects_or_structures(collection, "subjects")
            
    start_years = [2016, 2020, 2023]

    subjects_and_structures = pd.read_csv("subject_structure_map.csv", 
                                            sep=";",
                                            quotechar='"', 
                                            encoding="utf-8",
                                            dtype={
                                                "subjectid": "str",
                                                "name": "str"
                                            })

    types_torta = pd.read_csv("torta_tipologie.csv", encoding="utf-8")
    
    collection = connect_to_db("mongodb://localhost:27017/",  "admin", "amsacta_documenti")
    STRUCTURES_COLOR_MAP, STRUCTURES_PATTERN_MAP = map_subjects_or_structures(collection, type="structures", df_map=subjects_and_structures)
    PROJECTS_COLOR_MAP, PROJECTS_PATTERN_MAP = map_subjects_or_structures(collection, type="projectacronym")

    types = get_types(collection, collapse_types=True)

    TYPES_COLOR_MAP, TYPES_PATTERN_MAP = map_subjects_or_structures(collection, type="types")

    types_torta_plot, types_torta_filename = plot_pie_chart(types,
                                                            param="type",
                                                            threshold=0,
                                                            color_map=TYPES_COLOR_MAP,
                                                            pattern_map=TYPES_PATTERN_MAP)
    
    types_plot, types_filename = plot_histogram(types, 2016, 2025, 
                                                color_map=TYPES_COLOR_MAP, 
                                                pattern_map=TYPES_PATTERN_MAP,
                                                add_labels=True)
    grouped_types_plot, grouped_types_filename = plot_grouped_histogram(df=types,
                                                                        color_map=TYPES_COLOR_MAP,
                                                                        pattern_map=TYPES_PATTERN_MAP,
                                                                        add_labels=True)
    datasets_plot, datasets_filename = plot_histogram(types, 2016, 2025, 
                                                      type_filter=["dataset/software"],
                                                      color_map=TYPES_COLOR_MAP,
                                                      pattern_map=TYPES_PATTERN_MAP,
                                                      add_labels=True)
    grouped_datasets_plot, grouped_datasets_filename = plot_grouped_histogram(df=types,
                                                                                type_filter=["dataset/software"],
                                                                                color_map=TYPES_COLOR_MAP,
                                                                                pattern_map=TYPES_PATTERN_MAP,
                                                                                add_labels=True)
    sizes = get_filesize(collection)
    sizes_plot, sizes_filename = plot_size_histogram(sizes, min_year=2016, max_year=2025)
    grouped_sizes_plot, grouped_sizes_filename = plot_group_sizes(df=sizes)
    sizes_per_record = get_filesizes_per_dataset(collection)
    size_per_record_plot, size_per_record_filename = plot_size_histogram(sizes_per_record, 
                                                                            min_year=2016,
                                                                            max_year=2025,
                                                                            param="median_dataset_size",
                                                                            log_scale=False)
    grouped_median_sizes = get_grouped_median_sizes(collection)
    grouped_median_sizes_plot, grouped_median_sizes_filename = plot_size_histogram(df=grouped_median_sizes,
                                                                                    param="median_dataset_size",
                                                                                    x_axis="year_range",
                                                                                    log_scale=False)
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
                                                    plot_order=["has relatedid", "no relatedid"],
                                                    add_percentage=True)
    grouped_related_plot, grouped_related_filename = plot_grouped_histogram(df=related,
                                                                            filename="relatedid",
                                                                            color_map=RELATED_COLOR_MAP,
                                                                            pattern_map=RELATED_PATTERN_MAP,
                                                                            add_percentage=True)


    SUBJECTS_COLOR_MAP, SUBJECTS_PATTERN_MAP = map_subjects_or_structures(collection, type="subjects", df_map=subjects_and_structures)
    for start_year in start_years:
        end_year = start_year + 2 if start_year > 2016 else start_year + 3
        subjects = get_subjects_or_structures(collection)
        threshold = 5 if start_year > 2019 else 1
        subjects_plot, subjects_filename = plot_subject_chart(df=subjects,
                                                                param="subject",
                                                                threshold=threshold,
                                                                start_year=start_year,
                                                                end_year=end_year,
                                                                color_map=SUBJECTS_COLOR_MAP,
                                                                pattern_map=SUBJECTS_PATTERN_MAP)
        
    for start_year in start_years:
        end_year = start_year + 2 if start_year > 2016 else start_year + 3
        #threshold = 1 if start_year == 2023 else 0
        structures = get_subjects_or_structures(collection, type="structures")
        structures_plot, structures_filename = plot_structures(df=structures, 
                                            param="structure", 
                                            threshold=0, 
                                            min_year=start_year, 
                                            max_year=end_year,
                                            df_map=subjects_and_structures,
                                            color_scheme=STRUCTURES_COLOR_MAP,
                                            pattern_scheme=STRUCTURES_PATTERN_MAP)
    
    for start_year in start_years:
        param = "projectacronym"
        end_year = start_year + 2 if start_year > 2016 else start_year + 3
        threshold = 1 if start_year < 2023 else 2
        projects = get_funding_info(collection, param, start_year, end_year, get_all=True)
        projects_plot, projects_filename = plot_funding_treemap(projects, 
                                                                param, 
                                                                start_year, 
                                                                end_year,
                                                                color_scheme=PROJECTS_COLOR_MAP,
                                                                pattern_scheme=PROJECTS_PATTERN_MAP,
                                                                threshold=threshold)


if __name__ == "__main__":
    create_plots()
    save_all_figures(figures, scale=DEFAULT_SCALE, png=SAVE_PNG, svg=SAVE_SVG, use_cached=USE_CACHED_IMG)
    save_md_report(figures, report_filename="report.md")
    save_html_dashboard(figures, dashboard_filename="dashboard.html")