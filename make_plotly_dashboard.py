import graph
import pandas as pd


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
    f.write("Scarica il file CSV: <a href='" + types_filename + ".csv' download>Download CSV</a><br>")
    
    f.write(grouped_types_plot.to_html(full_html=False, include_plotlyjs="cdn"))
    f.write("Scarica il file CSV: <a href='" + grouped_types_filename + ".csv' download>Download CSV</a><br>")
    
    f.write(datasets_plot.to_html(full_html=False, include_plotlyjs=False))
    f.write("Scarica il file CSV: <a href='" + datasets_filename + ".csv' download>Download CSV</a><br>")
    
    f.write(grouped_datasets_plot.to_html(full_html=False, include_plotlyjs=False))
    f.write("Scarica il file CSV: <a href='" + grouped_datasets_filename + ".csv' download>Download CSV</a><br>")
    
    f.write("<h1>Dataset con collegamento a pubblicazione</h1>")
    
    f.write(related_plot.to_html(full_html=False, include_plotlyjs=False))
    f.write("Scarica il file CSV: <a href='" + related_filename + ".csv' download>Download CSV</a><br>")
    
    f.write(grouped_related_plot.to_html(full_html=False, include_plotlyjs=False))
    f.write("Scarica il file CSV: <a href='" + grouped_related_filename + ".csv' download>Download CSV</a><br>")
    
    f.write("<h1>Volume dei dataset</h1>")
    
    f.write(sizes_plot.to_html(full_html=False, include_plotlyjs=False))
    f.write("Scarica il file CSV: <a href='" + sizes_filename + ".csv' download>Download CSV</a><br>")
    
    f.write(grouped_sizes_plot.to_html(full_html=False, include_plotlyjs=False))
    f.write("Scarica il file CSV: <a href='" + grouped_sizes_filename + ".csv' download>Download CSV</a><br>")
    

    f.write("<h1>Settori disciplinari (dataset e software)</h1>")
    
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

    f.write("<h1>Strutture (dataset e software)</h1>")
    
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
        

    f.write("<h1>Progetti (dataset e software)</h1>")
    
    for start_year in start_years:
        param = "projectacronym"
        end_year = start_year + 2 if start_year > 2015 else start_year + 4
        projects = get_funding_info(collection, param, start_year, end_year, get_all=True)
        projects_plot, projects_filename = plot_funding_treemap(projects, param, start_year, end_year)
        f.write(projects_plot.to_html(full_html=False, include_plotlyjs=False))
        f.write("Scarica il file CSV: <a href='" + projects_filename + ".csv' download>Download CSV</a><br>")
        

    f.write("<h1>Enti finanziatori (dataset e software)</h1>")
    
    for start_year in start_years:
        end_year = start_year + 2 if start_year > 2015 else start_year + 4
        funders = get_funding_info(collection, "funder", start_year, end_year, get_all=True)
        funders_plot, funders_filename = plot_funding_treemap(funders, "funder", start_year, end_year)
        f.write(funders_plot.to_html(full_html=False, include_plotlyjs=False))
        f.write("Scarica il file CSV: <a href='" + funders_filename + ".csv' download>Download CSV</a><br>")
        

    f.write("<h1>Creatori (dataset e software)</h1>")
    
    for start_year in start_years:
        top_n = 50
        end_year = start_year + 2 if start_year > 2015 else start_year + 4
        creators = get_creators(collection, start_year, end_year)
        creators_plot, filename = plot_creators(creators, start_year, end_year, top_n=top_n)
        f.write(creators_plot.to_html(full_html=False, include_plotlyjs=False))
        f.write("Scarica il file CSV: <a href='" + filename + ".csv' download>Download CSV</a><br>")
        

    f.write("</body></html>")

