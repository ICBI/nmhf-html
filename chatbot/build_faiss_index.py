import json
import os
import numpy as np
import faiss
from sentence_transformers import SentenceTransformer
from google.cloud import bigquery

# ---------------------------------------------------------------------------
# Configuration & Setup
# ---------------------------------------------------------------------------
GCP_PROJECT   = "nmhf-477600"
DATASET       = "nmhf_info"
INDEX_OUTPUT_PATH    = "nmhf_faiss.index"
METADATA_OUTPUT_PATH = "nmhf_metadata.json"

# Tables to pull from
TABLES_CONFIG = [
    {"table": "school_data", "text_columns": ["variable_code", "variable_description"]},
    {"table": "minority_svi", "text_columns": [
        "Variable_or_Abbreviation", "Description", "Measure", "Notes",
        "Theme", "Source", "Date", "US_Census_Bureau_American_Community_Survey_Reference"
    ]},
    {"table": "acs_data", "text_columns": ["UniqueID", "Stub", "Data_Release"]},
    {"table": "coronavirus_case_data_2021", "text_columns": ["variable_code", "variable_description"]},
    {"table": "master_list_of_site_sources", "text_columns": ["Site", "Source", "Link", "Note"]},
    {"table": "area_health_resource", "text_columns": ["Access_Type", "Public"]},
    {"table": "census_redistricting_data", "text_columns": ["variable_code", "variable_description"]},
    {"table": "all_info", "text_columns": ["Data", "Source", "Link", "Description"]},
    {"table": "sdi", "text_columns": ["Field_name", "Type", "Description"]},
    {"table": "svi", "text_columns": ["variable_name_", "variable_label"]},
    {"table": "health_data", "text_columns": ["variable_code", "variable_description"]},
    {"table": "census_population_ethnicity", "text_columns": ["population_code", "population_description"]},
    {"table": "covid-19_insights", "text_columns": ["variable_code", "variable_description"]},
    {"table": "aqi", "text_columns": ["Field_Position", "Field_Name", "Description"]},
    {"table": "child_opportunity_index", "text_columns": ["Column", "Type", "Label", "Description"]},
    {"table": "socap", "text_columns": ["Access_Type", "Description"]},
    {"table": "county_health_data", "text_columns": ["Variables", "Description", "Trend_Data_Variables"]},
    {"table": "fbi_crime_data", "text_columns": ["variable_code", "variable_description"]},
    {"table": "coronavirus_case_data_2020", "text_columns": ["variable_code", "variable_description"]},
    {"table": "adi", "text_columns": ["State_abr", "State_full", "Records"]},
    {"table": "ahrq_sdoh", "text_columns": ["name", "label", "type", "length", "format"]},
    {"table": "ndi", "text_columns": ["Data_Attributes", "Format", "Data_Description"]},
    {"table": "social_explorer", "text_columns": ["Access_Type", "Institutional_with_account"]},
    {"table": "county_level_cancer_incidence_", "text_columns": ["Links"]},
    {"table": "eviction_rate", "text_columns": ["Access_Type", "Public"]},
    {"table": "income_inequality_saipe", "text_columns": ["Access_Type", "Public"]},
    {"table": "low_food_access_2", "text_columns": ["Data_Attributes", "Data_Types", "Data_Origin"]},
]

# ---------------------------------------------------------------------------
# Acronym Glossary
# ---------------------------------------------------------------------------
# For #2. Using explicit glossary chunks directly in the index
# rather than hoping the raw BigQuery metadata
# happens to spell out every acronym clearly enough for embedding
# similarity to catch it. 
# List is in sync with ACRONYM_MAP in app.py.
ACRONYM_MAP = {
    "ADI":  "Area Deprivation Index — ranks neighborhoods by socioeconomic disadvantage using factors like income, education, housing quality, and employment.",
    "SVI":  "Social Vulnerability Index — measures a community's relative vulnerability to external stressors like disasters, using census data on socioeconomic status, household composition, minority status, and housing/transportation.",
    "NDI":  "Neighborhood Deprivation Index — a composite measure of neighborhood-level socioeconomic deprivation, combining variables such as poverty, unemployment, education, and housing quality into a single score.",
    "SDOH": "Social Determinants of Health — the non-medical conditions in which people are born, grow, live, work, and age that influence health outcomes.",
    "NMHF": "Non-Medical Health Factors — Georgetown ICBI's term for the broader data ecosystem covering social, environmental, and economic drivers of health (overlaps with SDOH).",
    "AQI":  "Air Quality Index — an EPA measure of how polluted the air currently is or is forecast to become.",
    "ACS":  "American Community Survey — an ongoing U.S. Census Bureau survey providing detailed demographic, social, economic, and housing data.",
    "COI":  "Child Opportunity Index — measures neighborhood resources and conditions that affect children's healthy development.",
    "AHRQ": "Agency for Healthcare Research and Quality — a federal agency; the ahrq_sdoh table contains its SDOH-related dataset fields.",
    "FBI":  "Federal Bureau of Investigation — the fbi_crime_data table contains crime statistics sourced from FBI data.",
}

# ---------------------------------------------------------------------------
# Load Embedding Model
# ---------------------------------------------------------------------------
print("Loading Sentence Transformer model (BAAI/bge-base-en-v1.5)...")
model = SentenceTransformer('BAAI/bge-base-en-v1.5')

documents     = []
metadata_list = []

# ---------------------------------------------------------------------------
# Add Acronym Glossary Chunks First
# ---------------------------------------------------------------------------
print("Adding acronym glossary chunks...")
for acronym, expansion in ACRONYM_MAP.items():
    glossary_text = f"{acronym} stands for {expansion}"
    documents.append(glossary_text)
    metadata_list.append({
        "type":    "acronym_glossary",
        "acronym": acronym,
        "text":    glossary_text
    })

# ---------------------------------------------------------------------------
# Pull & Clean Metadata from BigQuery
# ---------------------------------------------------------------------------
print(f"Connecting to BigQuery project: {GCP_PROJECT}")
client = bigquery.Client(project=GCP_PROJECT)

for table_config in TABLES_CONFIG:
    table = table_config["table"]
    cols  = table_config["text_columns"]
    full_table = f"`{GCP_PROJECT}.{DATASET}.{table}`"

    try:
        query = f"""
            SELECT {', '.join(f'`{c}`' for c in cols)}
            FROM {full_table}
            WHERE `{cols[0]}` IS NOT NULL
        """
        print(f"Pulling from {DATASET}.{table}...")
        df = client.query(query).to_dataframe()
        print(f"  → {len(df)} rows retrieved")

        if df.empty:
            continue

        # ── Clean ──────────────────────────────────────────────
        df = df.drop_duplicates(subset=[cols[0]])   # deduplicate on variable name
        df = df.fillna("")                           # fill nulls with empty string
        for col in cols:
            df[col] = df[col].astype(str).str.strip()

        # ── 1. Dataset-level summary chunk ──────────────────────
        dataset_chunk = (
            f"Dataset: {table}. "
            f"Contains {len(df)} records and {len(cols)} variables. "
            f"Variables included: {', '.join(cols)}"
        )
        documents.append(dataset_chunk)
        metadata_list.append({
            "type":       "dataset_summary",
            "table_name": table,
            "columns":    cols,
            "text":       dataset_chunk
        })

        # ── 2. Variable-level chunks (one per row) ──────────────

        for _, row in df.iterrows():
            parts = []
            for col in cols:
                val = str(row.get(col, "")).strip()
                if val and val not in ("", "nan", "None"):
                    parts.append(f"{col}: {val}")
            var_text = " | ".join(parts)

            if len(var_text.split()) < 3:
                continue

            documents.append(var_text)
            metadata_list.append({
                "type":       "variable_definition",
                "table_name": table,
                "label":      row.get(cols[0], ""),
                "text":       var_text,
                "metadata":   {col: row.get(col, "") for col in cols}
            })

    except Exception as e:
        print(f"Error processing table '{table}': {e}")

print(f"\nTotal knowledge chunks generated: {len(documents)}")

# ---------------------------------------------------------------------------
# Build FAISS Vector Index
# ---------------------------------------------------------------------------
print("Generating embeddings (this may take a few minutes)...")
embeddings = model.encode(
    documents,
    convert_to_numpy=True,
    show_progress_bar=True
)

faiss.normalize_L2(embeddings)

dimension = embeddings.shape[1]
index = faiss.IndexFlatIP(dimension)
index.add(embeddings)

print(f"FAISS index built successfully with {index.ntotal} vectors.")

# ---------------------------------------------------------------------------
# Sanity Check
# ---------------------------------------------------------------------------
print("\n─ Sanity check ─")
test_queries = ["What is adult smoking?", "NDI", "median income data"]
for test_query in test_queries:
    test_embed = model.encode([test_query], convert_to_numpy=True)
    faiss.normalize_L2(test_embed)
    D, I = index.search(test_embed, k=3)
    print(f"\nQuery: '{test_query}'")
    for rank, (dist, idx) in enumerate(zip(D[0], I[0])):
        print(f"  #{rank+1} (score={dist:.4f}): {metadata_list[idx]['text'][:120]}")

# ---------------------------------------------------------------------------
# Save Index and Metadata to Disk
# ---------------------------------------------------------------------------
print(f"\nSaving FAISS index to {INDEX_OUTPUT_PATH}...")
faiss.write_index(index, INDEX_OUTPUT_PATH)

print(f"Saving metadata mapping to {METADATA_OUTPUT_PATH}...")
with open(METADATA_OUTPUT_PATH, "w", encoding="utf-8") as f:
    json.dump(metadata_list, f, indent=2)

print("\nDone! Both index and metadata files are ready.")
print(f"Copy '{INDEX_OUTPUT_PATH}' and '{METADATA_OUTPUT_PATH}' into your app.py project directory")
print("so they get picked up by the Docker COPY step.")
