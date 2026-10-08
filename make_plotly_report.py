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

with open("report.md", "w") as r:
    for start_year in start_years:
        end_year = start_year + 2 if start_year > 2015 else start_year + 4
        subjects = get_subjects_or_structures(collection)
        threshold = 5 if start_year > 2019 else 1
        subjects_plot, subjects_filename = plot_subject_chart(df=subjects, param="subject", threshold=threshold, start_year=start_year, end_year=end_year)
        simple_subjects_plot, simple_subjects_filename = plot_simple_subject_chart(df=subjects, param="subject", threshold=threshold, start_year=start_year, end_year=end_year)
    
    for start_year in start_years:
        end_year = start_year + 2 if start_year > 2015 else start_year + 4
        structures = get_subjects_or_structures(collection, type="structures")
        structures_plot, structures_filename = plot_structures(df=structures, 
                                            param="structure", 
                                            threshold=0, 
                                            min_year=start_year, 
                                            max_year=end_year,
                                            df_map=subjects_and_structures)
        
    for start_year in start_years:
        param = "projectacronym"
        end_year = start_year + 2 if start_year > 2015 else start_year + 4
        projects = get_funding_info(collection, param, start_year, end_year, get_all=True)
        projects_plot, projects_filename = plot_funding_treemap(projects, param, start_year, end_year)
        
    for start_year in start_years:
        end_year = start_year + 2 if start_year > 2015 else start_year + 4
        funders = get_funding_info(collection, "funder", start_year, end_year, get_all=True)
        funders_plot, funders_filename = plot_funding_treemap(funders, "funder", start_year, end_year)
        
    for start_year in start_years:
        top_n = 50
        end_year = start_year + 2 if start_year > 2015 else start_year + 4
        creators = get_creators(collection, start_year, end_year)
        creators_plot, filename = plot_creators(creators, start_year, end_year, top_n=top_n)
        
        
        

    

