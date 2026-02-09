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
LIMIT_TEST = 10 

client = OpenAI(api_key=API_KEY, base_url=ENDPOINT_URL, timeout=120.0)

def load_system_prompt(filename="nace-llm-review/system_prompt.md"):
    if os.path.exists(filename):
        with open(filename, "r", encoding="utf-8") as f:
            return f.read()
    return "You are a NACE expert. Audit consistency and return JSON."

def audit_nace_expert():
    print("Chargement des fichiers...")
    system_prompt_content = load_system_prompt()
    
    try:
        df_index = pd.read_excel("NACE Rev. 2.1 - Index entries - first batch-1090 entries - oct 2025.xlsx", header=1, dtype={'CODE': str})
        df_notes = pd.read_excel("NACE_Rev2.1_Structure_Explanatory_Notes_EN.xlsx", dtype={'CODE': str})
    except Exception as e:
        print(f"Erreur fichiers : {e}")
        return

    if TEST_MODE:
        df_index = df_index.head(LIMIT_TEST)

    results = []

    for i, row in df_index.iterrows():
        entry = str(row['INDEX ENTRY'])
        code = str(row['CODE']).strip()
        
        # Récupération des notes
        note_row = df_notes[df_notes['CODE'] == code]
        if note_row.empty:
            continue
        
        heading = note_row.iloc[0].get('HEADING', 'N/A')
        includes = note_row.iloc[0].get('Includes', 'None')
        includes_also = note_row.iloc[0].get('IncludesAlso', 'None')
        excludes = note_row.iloc[0].get('Excludes', 'None')

        # Construction du prompt utilisateur (Format spécifique demandé)
        user_prompt = f"""### DATA TO AUDIT
- **INDEX ENTRY:** {entry}
- **ASSIGNED CODE:** {code}

### REFERENCE EXPLANATORY NOTES (NACE Rev. 2.1)
- **HEADING:** {heading}
- **INCLUDES:** {includes}
- **INCLUDES ALSO:** {includes_also}
- **EXCLUDES:** {excludes}

### TASK
Evaluate the consistency of the INDEX ENTRY with the REFERENCE EXPLANATORY NOTES. 
Return the result in the required JSON format."""

        success = False
        retries = 0
        while not success and retries < 3:
            try:
                response = client.chat.completions.create(
                    model=MODEL,
                    messages=[
                        {"role": "system", "content": system_prompt_content},
                        {"role": "user", "content": user_prompt}
                    ],
                    temperature=0
                )
                
                content = response.choices[0].message.content
                # Nettoyage robuste du JSON (enlève les balises markdown)
                clean_content = content.replace("```json", "").replace("```", "").strip()
                res_json = json.loads(clean_content)
                
                results.append({
                    "Index_Entry": entry,
                    "NACE_Code": f"'{code}",
                    "Is_Consistent": res_json.get("is_consistent"),
                    "Justification": res_json.get("justification"),
                    "Confidence_Score": res_json.get("confidence_score"),
                    "Heading_Ref": heading
                })
                print(f"[{i+1}/{len(df_index)}] Analysé : {code}")
                success = True

            except Exception as e:
                error_str = str(e)
                if "504" in error_str or "timeout" in error_str.lower():
                    retries += 1
                    time.sleep(30 * retries)
                else:
                    print(f"Erreur ligne {i} : {e}")
                    break

        # Sauvegarde intermédiaire toutes les 10 lignes pour ne rien perdre
        if (i + 1) % 10 == 0:
            pd.DataFrame(results).to_csv("partial_results.csv", index=False, sep=';', encoding='utf-8-sig')

    # Exportation finale
    df_final = pd.DataFrame(results)
    output_name = "nace_audit_test.csv" if TEST_MODE else "nace_index_audit.csv"
    df_final.to_csv(output_name, index=False, sep=';', encoding='utf-8-sig')
    print(f"\nTerminé ! Fichier : {output_name}")

if __name__ == "__main__":
    audit_nace_expert()