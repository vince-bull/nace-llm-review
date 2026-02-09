import pandas as pd
import json
import time
import os
from openai import OpenAI 

# --- CONFIGURATION ---
API_KEY = os.getenv('API_KEY')
ENDPOINT_URL = "https://llm.lab.sspcloud.fr/api/v1/"
MODEL = "model-vince"

TEST_MODE = False 
LIMIT_TEST = 50 

# Initialisation du client compatible OpenAI
client = OpenAI(
    api_key=API_KEY,
    base_url=ENDPOINT_URL
)

def audit_nace_openai():
    print("Chargement des fichiers...")
    try:
        df_index = pd.read_excel(
            "NACE Rev. 2.1 - Index entries - first batch-1090 entries - oct 2025.xlsx", 
            header=1, 
            dtype={'CODE': str}
        )
        df_notes = pd.read_excel(
            "NACE_Rev2.1_Structure_Explanatory_Notes_EN.xlsx", 
            dtype={'CODE': str}
        )
    except Exception as e:
        print(f"Erreur fichiers : {e}")
        return

    if TEST_MODE:
        df_index = df_index.head(LIMIT_TEST)

    results = []

    for i, row in df_index.iterrows():
        entry = str(row['INDEX ENTRY'])
        code = str(row['CODE']).strip()
        
        # Récupération des notes correspondantes
        note_row = df_notes[df_notes['CODE'] == code]
        if note_row.empty:
            continue
        
        heading = note_row.iloc[0].get('HEADING', 'N/A')
        includes = note_row.iloc[0].get('Includes', 'None')
        includes_also = note_row.iloc[0].get('IncludesAlso', 'None')
        excludes = note_row.iloc[0].get('Excludes', 'None')

        # Construction des messages
        system_msg = "You are a NACE expert. Answer ONLY with a valid JSON object: {\"is_consistent\": bool, \"justification\": \"string\"}"
        user_msg = (
            f"INDEX ENTRY: {entry}\nCODE: {code}\n"
            f"HEADING: {heading}\nINCLUDES: {includes}\n"
            f"INCLUDES ALSO: {includes_also}\nEXCLUDES: {excludes}"
        )

        success = False
        retries = 0
        while not success and retries < 3:
            try:
                # Appel via le SDK OpenAI
                response = client.chat.completions.create(
                    model=MODEL,
                    messages=[
                        {"role": "system", "content": system_msg},
                        {"role": "user", "content": user_msg}
                    ],
                    temperature=0
                )
                
                content = response.choices[0].message.content
                
                # Nettoyage et parsing du JSON
                clean_content = content.replace("```json", "").replace("```", "").strip()
                res_json = json.loads(clean_content)
                
                results.append({
                    "Index_Entry": entry,
                    "NACE_Code": f"'{code}",
                    "Heading_Reference": heading,
                    "Is_Consistent": res_json.get("is_consistent"),
                    "Justification": res_json.get("justification")
                })
                print(f"[{i+1}/{len(df_index)}] OK : {code}")
                success = True

            except Exception as e:
                # Gestion spécifique des erreurs
                if "429" in str(e):
                    print(f"Rate limit atteint, pause de 20s...")
                    time.sleep(20)
                    retries += 1
                else:
                    print(f"Erreur ligne {i} : {e}")
                    # En cas d'erreur de parsing ou autre, on note l'erreur pour ne pas bloquer
                    results.append({
                        "Index_Entry": entry, "NACE_Code": code, "Is_Consistent": "ERROR", "Justification": str(e)
                    })
                    break

    # Exportation finale en CSV
    df_final = pd.DataFrame(results)
    output_name = "nace_audit_test.csv" if TEST_MODE else "nace_audit_full.csv"
    df_final.to_csv(output_name, index=False, sep=';', encoding='utf-8-sig')
    print(f"\nTerminé ! Fichier généré : {output_name}")

if __name__ == "__main__":
    audit_nace_openai()