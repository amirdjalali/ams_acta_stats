from pymongo import MongoClient
import pandas as pd
import matplotlib.pyplot as plt
import plotly.express as px
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import plotly.io as pio

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

def plot_subject_chart(df, param, threshold=0, start_year=None, end_year=None):
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
    fig2 = px.sunburst(df_clean, path=["macro_sector", "subject"], values="count", title=f"Subjects Distribution, {start_year}-{end_year}")
    #fig2.show()  # opens in browser
    filename = f"{OUT_DIR}/{param}_{start_year}-{end_year}"
    df_clean.to_csv(f"{filename}.csv", index=False, encoding="utf-8")
    fig2.write_image(f"{filename}.png")

    return fig2, filename

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
    counts[["macro_sector"]].to_csv(f"{filename}.csv", index=False, encoding="utf-8")
    fig.write_image(f"{filename}.png")
    return fig, filename

def plot_size_histogram(df, min_year=None, max_year=None):
    df_filtered = df[(df["year"] >= min_year) & (df["year"] <= max_year)]
    df_filtered["total_filesize"] = df_filtered["total_filesize"] / (1024 ** 3)
    fig = px.histogram(
        df_filtered,
        x=df_filtered["year"].astype(str),
        y="total_filesize",
        title="Total Filesize by Year (GB, log scale)",
        log_y=True
    )
    fig.update_yaxes(
        title_text="",        # remove y axis label
        tickmode="array",
        tickvals=[.001, .01, .1, 1, 10, 100, 1000, 10000]
    )
    filename = f"{OUT_DIR}/sizes_{min_year}-{max_year}"
    df_filtered.to_csv(f"{filename}.csv", index=False, encoding="utf-8")
    fig.write_image(f"{filename}.png")
    return fig, filename

def plot_group_sizes(df, start_years=[2015, 2020, 2023, 2026]):
    bins = sorted(start_years)
    labels = [f"{s}-{e - 1}" for s, e in zip(bins[:-1], bins[1:])]
    df_filtered = df[(df["year"] >= bins[0]) & (df["year"] < bins[-1])].copy()
    df_filtered["total_filesize"] = df_filtered["total_filesize"] / (1024 ** 3)  # bytes -> GB

    df_filtered["year_range"] = pd.cut(    # labels the rows according to the bin values, excluding the right value
        df_filtered["year"], bins=bins, labels=labels, right=False
    )

    df_grouped = (  # groups the values by year_range
        df_filtered
        .groupby("year_range", observed=False, as_index=False)["total_filesize"]
        .sum()
    )

    fig = px.bar(
        df_grouped,
        x="year_range",
        y="total_filesize",
        title="Total Filesize by Year Range (GB, log scale)",
        log_y=True,
    )
    fig.update_xaxes(title_text="")
    fig.update_yaxes(
        title_text="",
        tickmode="array",
        tickvals=[.001, .01, .1, 1, 10, 100, 1000, 10000],
    )

    filename = "sizes_"
    for label in labels:
        filename += label + "_"

    filename = f"{OUT_DIR}/{filename}"
    df_grouped.to_csv(f"{filename}.csv", index=False, encoding="utf-8")
    fig.write_image(f"{filename}.png")
    return fig, filename

def plot_histogram(df, min_year=0, max_year=9999, type_filter=None, filename="documents", collapse_all=True):
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
        x=df_filtered["year"].astype(str),
        y="count",
        color="type",
        title=f"Documents by Year, {min_year}-{max_year}" + (f" — {type_filter}" if type_filter else ""),
        barmode="stack"
        )
    
    filename = f"{OUT_DIR}/{filename}_{min_year}-{max_year}" + (f"_{filter_string}" if filter_string else "")
    df_filtered.to_csv(f"{filename}.csv", index=False, encoding="utf-8")
    fig.write_image(f"{filename}.png")
    return fig, filename

def plot_grouped_histogram(df, bins=[2015, 2020, 2023, 2026], type_filter=None, filename="documents", collapse_all=True):
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

    print(df_grouped)
    fig = px.bar(
            df_grouped,
            x=df_grouped["year_range"].astype(str),
            y="count",
            color="type",
            title=f"Documents by Year" + (f" — {type_filter}" if type_filter else ""),
            barmode="stack"
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
        title=f"Funding information ({param}), {min_year}-{max_year}"
    )
    filename = f"{OUT_DIR}/{param}_{min_year}-{max_year}"
    df_grouped.to_csv(f"{filename}.csv", index=False, encoding="utf-8")
    fig.write_image(f"{filename}.png")
    return fig, filename

def plot_structures(df, param, min_year="", max_year="", threshold=1, df_map=None):
    df_filtered = df[(df["year"] >= min_year) & (df["year"] <= max_year)]
    df_filtered[param] = df.apply(
        lambda r: r[param] if r["count"] > threshold else "Other", axis=1
    )
    # merge all Other rows into one
    df_grouped = df_filtered.groupby(param)["count"].sum().reset_index()
    if map:
        df_grouped = (df_grouped.merge(df_map, left_on="structure", right_on="subjectid", how="left")
                      .drop(columns=["subjectid", "structure"])
                      .rename(columns={"name": param}))
        df_grouped["structure"] = df_grouped["structure"].str.split(" - ").str[-1]
        print(df_grouped)
    fig = px.treemap(
        df_grouped,
        path=[param],
        values="count",
        title=f"Structures, {min_year}-{max_year}"
    )
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

if __name__ == "__main__":
    start_years = [2015, 2020, 2023]

    subjects_and_structures = pd.read_csv("subject_structure_map.csv", sep=";", quotechar='"', encoding="utf-8")
    
    collection = connect_to_db("mongodb://localhost:27017/",  "admin", "amsacta_documenti")

    types = get_types(collection)
    print(types)
    types_plot, types_filename = plot_histogram(types, 2015, 2025)
    grouped_types_plot, grouped_types_filename = plot_grouped_histogram(df=types)
    datasets_plot, datasets_filename = plot_histogram(types, 2015, 2025, type_filter=["dataset", "software"], collapse_all=True)
    grouped_datasets_plot, grouped_datasets_filename = plot_grouped_histogram(df=types, type_filter=["dataset", "software"], collapse_all=True)
    sizes = get_filesize(collection)
    sizes_plot, sizes_filename = plot_size_histogram(sizes, 2015, 2025)
    grouped_sizes_plot, grouped_sizes_filename = plot_group_sizes(df=sizes)
    related = get_related_id(collection)
    related = related.rename(columns={"has_relatedid": "type"})
    related["type"] = related["type"].map({True: "has relatedid", False: "no relatedid"})
    related_plot, related_filename = plot_histogram(related, min_year=2017, max_year=2025, filename="relatedid")
    grouped_related_plot, grouped_related_filename = plot_grouped_histogram(df=related, filename="relatedid")

    with open("dashboard.html", "w") as f, open("report.md", "w") as r:
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

        r.write("# Report AMS Acta\n")

        f.write("<h1>Documenti per tipologia</h1>")
        r.write("\n## Documenti per tipologia\n")
        f.write(types_plot.to_html(full_html=False, include_plotlyjs="cdn"))
        f.write("Scarica il file CSV: <a href='" + types_filename + ".csv' download>Download CSV</a><br>")
        r.write(f"\n![Documenti per tipologia]({types_filename}.png)\n\nScarica il file CSV: [{types_filename}.csv]({types_filename}.csv)\n")
        f.write(grouped_types_plot.to_html(full_html=False, include_plotlyjs="cdn"))
        f.write("Scarica il file CSV: <a href='" + grouped_types_filename + ".csv' download>Download CSV</a><br>")
        r.write(f"\n![Documenti per tipologia]({grouped_types_filename}.png)\n\nScarica il file CSV: [{grouped_types_filename}.csv]({grouped_types_filename}.csv)\n")
        f.write(datasets_plot.to_html(full_html=False, include_plotlyjs=False))
        f.write("Scarica il file CSV: <a href='" + datasets_filename + ".csv' download>Download CSV</a><br>")
        r.write(f"\n![Documenti per tipologia]({datasets_filename}.png)\n\nScarica il file CSV: [{datasets_filename}.csv]({datasets_filename}.csv)\n")
        f.write(grouped_datasets_plot.to_html(full_html=False, include_plotlyjs=False))
        f.write("Scarica il file CSV: <a href='" + grouped_datasets_filename + ".csv' download>Download CSV</a><br>")
        r.write(f"\n![Documenti per tipologia]({grouped_datasets_filename}.png)\n\nScarica il file CSV: [{grouped_datasets_filename}.csv]({grouped_datasets_filename}.csv)\n")
        f.write("<h1>Dataset con collegamento a pubblicazione</h1>")
        r.write("\n## Dataset con collegamento a pubblicazione\n")
        f.write(related_plot.to_html(full_html=False, include_plotlyjs=False))
        f.write("Scarica il file CSV: <a href='" + related_filename + ".csv' download>Download CSV</a><br>")
        r.write(f"\n![Dataset con collegamento a pubblicazione]({related_filename}.png)\n\nScarica il file CSV: [{related_filename}.csv]({related_filename}.csv)\n")
        f.write(grouped_related_plot.to_html(full_html=False, include_plotlyjs=False))
        f.write("Scarica il file CSV: <a href='" + grouped_related_filename + ".csv' download>Download CSV</a><br>")
        r.write(f"\n![Dataset con collegamento a pubblicazione]({grouped_related_filename}.png)\n\nScarica il file CSV: [{grouped_related_filename}.csv]({grouped_related_filename}.csv)\n")
        f.write("<h1>Volume dei dataset</h1>")
        r.write("\n## Volume dei dataset\n")
        f.write(sizes_plot.to_html(full_html=False, include_plotlyjs=False))
        f.write("Scarica il file CSV: <a href='" + sizes_filename + ".csv' download>Download CSV</a><br>")
        r.write(f"\n![Volume dei dataset]({sizes_filename}.png)\n\nScarica il file CSV: [{sizes_filename}.csv]({sizes_filename}.csv)\n")
        f.write(grouped_sizes_plot.to_html(full_html=False, include_plotlyjs=False))
        f.write("Scarica il file CSV: <a href='" + grouped_sizes_filename + ".csv' download>Download CSV</a><br>")

        f.write("<h1>Settori disciplinari (dataset e software)</h1>")
        r.write("\n## Settori disciplinari\n")
        for start_year in start_years:
            end_year = start_year + 2 if start_year > 2015 else start_year + 4
            subjects = get_subjects_or_structures(collection)
            threshold = 5 if start_year > 2019 else 1
            subjects_plot, subjects_filename = plot_subject_chart(df=subjects, param="subject", threshold=threshold, start_year=start_year, end_year=end_year)
            simple_subjects_plot, simple_subjects_filename = plot_simple_subject_chart(df=subjects, param="subject", threshold=threshold, start_year=start_year, end_year=end_year)
            f.write(subjects_plot.to_html(full_html=False, include_plotlyjs=False))
            f.write("Scarica il file CSV: <a href='" + subjects_filename + ".csv' download>Download CSV</a><br>")
            f.write(simple_subjects_plot.to_html(full_html=False, include_plotlyjs=False))
            f.write("Scarica il file CSV: <a href='" + simple_subjects_filename + ".csv' download>Download CSV</a><br>")
            r.write(f"\n![Settori disciplinari]({subjects_filename}.png)\n\nScarica il file CSV: [{subjects_filename}.csv]({subjects_filename}.csv)\n")
            r.write(f"\n![Settori disciplinari (semplice)]({simple_subjects_filename}.png)\n\nScarica il file CSV: [{simple_subjects_filename}.csv]({simple_subjects_filename}.csv)\n")

        f.write("<h1>Strutture (dataset e software)</h1>")
        r.write("\n## Strutture\n")
        for start_year in start_years:
            end_year = start_year + 2 if start_year > 2015 else start_year + 4
            structures = get_subjects_or_structures(collection, type="structures")
            structures_plot, structures_filename = plot_structures(df=structures, 
                                              param="structure", 
                                              threshold=0, 
                                              min_year=start_year, 
                                              max_year=end_year,
                                              df_map=subjects_and_structures)
            f.write(structures_plot.to_html(full_html=False, include_plotlyjs=False))
            f.write("Scarica il file CSV: <a href='" + structures_filename + ".csv' download>Download CSV</a><br>")
            r.write(f"\n![Strutture]({structures_filename}.png)\n\nScarica il file CSV: [{structures_filename}.csv]({structures_filename}.csv)\n")

        f.write("<h1>Progetti (dataset e software)</h1>")
        r.write("\n## Progetti\n")
        for start_year in start_years:
            param = "projectacronym"
            end_year = start_year + 2 if start_year > 2015 else start_year + 4
            projects = get_funding_info(collection, param, start_year, end_year)
            projects_plot, projects_filename = plot_funding_treemap(projects, param, start_year, end_year)
            f.write(projects_plot.to_html(full_html=False, include_plotlyjs=False))
            f.write("Scarica il file CSV: <a href='" + projects_filename + ".csv' download>Download CSV</a><br>")
            r.write(f"\n![Progetti]({projects_filename}.png)\n\nScarica il file CSV: [{projects_filename}.csv]({projects_filename}.csv)\n")

        f.write("<h1>Enti finanziatori (dataset e software)</h1>")
        r.write("\n## Enti finanziatori\n")
        for start_year in start_years:
            end_year = start_year + 2 if start_year > 2015 else start_year + 4
            funders = get_funding_info(collection, "funder", start_year, end_year)
            funders_plot, funders_filename = plot_funding_treemap(funders, "funder", start_year, end_year)
            f.write(funders_plot.to_html(full_html=False, include_plotlyjs=False))
            f.write("Scarica il file CSV: <a href='" + funders_filename + ".csv' download>Download CSV</a><br>")
            r.write(f"\n![Enti finanziatori]({funders_filename}.png)\n\nScarica il file CSV: [{funders_filename}.csv]({funders_filename}.csv)\n")

        f.write("<h1>Creatori (dataset e software)</h1>")
        r.write("\n## Creatori\n")
        for start_year in start_years:
            top_n = 50
            end_year = start_year + 2 if start_year > 2015 else start_year + 4
            creators = get_creators(collection, start_year, end_year)
            creators_plot, filename = plot_creators(creators, start_year, end_year, top_n=top_n)
            f.write(creators_plot.to_html(full_html=False, include_plotlyjs=False))
            f.write("Scarica il file CSV: <a href='" + filename + ".csv' download>Download CSV</a><br>")
            r.write(f"\n![Creatori]({filename}.png)\n\nScarica il file CSV: [{filename}.csv]({filename}.csv)\n")

        f.write("</body></html>")
