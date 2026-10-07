import unicodedata
import re
from pathlib import Path
import pandas as pd


# 1. CHARGEMENT

def load_raw(path: Path) -> pd.DataFrame:
    """
    Load the raw data from a CSV file into a pandas DataFrame.

    Parameters:
    path (Path): The path to the CSV file.

    Returns:
    pd.DataFrame: The loaded DataFrame.
    """
    try:
        df = pd.read_csv(path, sep=";", encoding="utf-8", dtype={"Code postal": str, "id": str}, \
            usecols=["id", "Adresse", "Code postal", "Ville", "Département", "code_departement", "Région", \
                     "pop", "geom", "Automate 24-24 (oui/non)", "Prix Gazole mis à jour le", "Prix Gazole",
                     "Prix SP95 mis à jour le","Prix SP95","Prix E85 mis à jour le","Prix E85", \
                    "Prix GPLc mis à jour le","Prix GPLc","Prix E10 mis à jour le","Prix E10","Prix SP98 mis à jour le","Prix SP98"], \
                        decimal=".")
        return df
    except FileNotFoundError:
        print(f"File not found: {path}")
        return pd.DataFrame()  # Return an empty DataFrame if the file is not found
    except Exception as e:
        print(f"An error occurred while loading the data: {e}")
        return pd.DataFrame()  # Return an empty DataFrame for any other exceptions


# NETTOYAGE DES DONNÉES
# 2.  NETTOYAGE DES NOMS DE COLONNES

def normalize_column_names(df: pd.DataFrame) -> pd.DataFrame:
    """
    Normalize DataFrame column names for BigQuery:
    - lowercase
    - remove accents
    - replace spaces with underscores
    - keep only letters, numbers and underscores
    - remove consecutive underscores
    - remove underscores at the beginning/end
    """

    def normalize(col: str) -> str:
        # Remove accents
        col = (
            unicodedata.normalize("NFKD", col).encode("ascii", "ignore").decode("utf-8"))

        # Lowercase
        col = col.lower()

        # Replace any character that is not a-z, 0-9 or _
        col = re.sub(r"[^a-z0-9_]", "_", col)

        # Replace multiple underscores with one
        col = re.sub(r"_+", "_", col)

        # Remove underscores at beginning/end
        col = col.strip("_")

        return col

    df.columns = df.columns.map(normalize)

    return df


# 2.2 NETTOYAGE DES COORDONNÉES
def fix_coordinates(df: pd.DataFrame) -> pd.DataFrame:
    """
    Extract latitude and longitude from the geom column and convert them to numeric values.
    Fix the latitude and longitude columns in the DataFrame by ensuring they are numeric and handling any non-numeric values.

    Parameters:
    df (pd.DataFrame): The DataFrame containing latitude and longitude columns.

    Returns:
    pd.DataFrame: The DataFrame with fixed latitude and longitude columns.
    """
    coordinates = df["geom"].str.split(",", expand=True)

    df["latitude"] = pd.to_numeric(coordinates[0], errors="coerce")
    df["longitude"] = pd.to_numeric(coordinates[1], errors="coerce")

    return df

# 4. CONVERSION DES TYPES DE DONNÉES
def cast_types(df: pd.DataFrame) -> pd.DataFrame:
    """
    Cast the data types of specific columns in the DataFrame to appropriate types.

    Parameters:
    df (pd.DataFrame): The DataFrame whose column types are to be cast.

    Returns:
    pd.DataFrame: The DataFrame with casted column types.
    """
    df['code_departement'] = df['code_departement'].astype(str)
    df['prix_gazole'] = pd.to_numeric(df['prix_gazole'], errors='coerce')
    df['prix_sp95'] = pd.to_numeric(df['prix_sp95'], errors='coerce')
    df['prix_e10'] = pd.to_numeric(df['prix_e10'], errors='coerce')
    df['prix_sp98'] = pd.to_numeric(df['prix_sp98'], errors='coerce')
    df['prix_e85'] = pd.to_numeric(df['prix_e85'], errors='coerce')
    df['prix_gplc'] = pd.to_numeric(df['prix_gplc'], errors='coerce')
    df['gazole_maj'] = pd.to_datetime(df['prix_gazole_mis_a_jour_le'], errors='coerce', utc=True)
    df['sp95_maj'] = pd.to_datetime(df['prix_sp95_mis_a_jour_le'], errors='coerce', utc=True)
    df['e10_maj'] = pd.to_datetime(df['prix_e10_mis_a_jour_le'], errors='coerce', utc=True)
    df['sp98_maj'] = pd.to_datetime(df['prix_sp98_mis_a_jour_le'], errors='coerce', utc=True)
    df['e85_maj'] = pd.to_datetime(df['prix_e85_mis_a_jour_le'], errors='coerce', utc=True)
    df['gplc_maj'] = pd.to_datetime(df['prix_gplc_mis_a_jour_le'], errors='coerce', utc=True)
    return df

# 5. TRANSFORMATION EN FORMAT LONG
def to_long_format(df: pd.DataFrame) -> pd.DataFrame:
    """
    Convert the DataFrame from wide format to long format for price columns.

    Parameters:
    df (pd.DataFrame): The DataFrame in wide format.

    Returns:
    pd.DataFrame: The DataFrame in long format with 'fuel_type' and 'price' columns.
    """
    price_columns = ['prix_gazole','prix_sp95','prix_e10','prix_sp98','prix_e85','prix_gplc']

    price_maj_columns = ['gazole_maj','sp95_maj','e10_maj','sp98_maj','e85_maj','gplc_maj']

    id_columns = ['id','adresse','code_postal','ville','departement',\
                'code_departement','region','pop','latitude','longitude','geom','automate_24_24_oui_non']

    df_prices = df.melt(id_vars=id_columns,value_vars=price_columns,var_name='carburant',value_name='prix')

    df_maj = df.melt(id_vars=id_columns,value_vars=price_maj_columns,var_name='carburant',value_name='maj')

    df_prices['carburant'] = (df_prices['carburant'].str.replace('prix_', '', regex=False))

    df_maj['carburant'] = (df_maj['carburant'].str.replace('_maj', '', regex=False))

    df_long = df_prices.merge(df_maj[id_columns + ['carburant', 'maj']],on=id_columns + ['carburant'],how='left')
    
    return df_long

# 6. SUPPRESSION DES PRIX INVALIDES
def drop_invalid_prices(df: pd.DataFrame, lo: float = 0.5, hi: float = 5.0) -> pd.DataFrame:
    """
    Drop rows from the DataFrame where any of the price columns have values outside the specified range.

    Parameters:
    df (pd.DataFrame): The DataFrame to filter.
    lo (float): The lower bound for valid price values.
    hi (float): The upper bound for valid price values.

    Returns:
    pd.DataFrame: The filtered DataFrame with invalid price rows dropped.
    """
    price_columns = ['prix']
    for col in price_columns:
        df = df[(df[col] >= lo) & (df[col] <= hi)]
    return df

# 7. PIPELINE DE NETTOYAGE DES DONNÉES
"""
Apply a series of cleaning functions to the DataFrame in a pipeline fashion. 
Each function is applied sequentially to transform the DataFrame into a clean and usable format for analysis.
"""
  
  
def clean(df: pd.DataFrame) -> pd.DataFrame:
    return (
        df
        .pipe(normalize_column_names)
        .pipe(fix_coordinates)
        .pipe(cast_types)
        .pipe(to_long_format)
        .pipe(drop_invalid_prices)
    )


# 8. VALIDATION DES DONNÉES
def validate(df: pd.DataFrame) -> pd.DataFrame:

    # Prix présents : doivent être dans une plage raisonnable
    assert df["prix"].dropna().between(0.5, 5).all(), \
        "Prix hors plage"

    # Latitude présente : doit être en France métropolitaine
    assert df["latitude"].dropna().between(41, 52).all(), \
        "Latitude hors France métropolitaine"

    # Unicité de (id, carburant)
    #assert not df.duplicated(["id", "carburant"]).any(), "Doublons détectés pour (id, carburant)"

    # Aucune colonne entièrement vide
    assert not df.isna().all().any(), \
        "Une colonne est entièrement vide"

    return df

# 9. ECRITURE DU RESULTAT

# DEFAULT_RAW = Path("data/raw/prix-des-carburants-en-france-flux-instantane-v2.csv")
# DEFAULT_PROCESSED = Path("data/processed/carburants_clean.csv")

# Chemins resolus depuis l'emplacement de ce fichier, et non depuis le
# repertoire de travail : les scripts fonctionnent donc qu'on les lance
# depuis la racine du projet, depuis src/, ou depuis un notebook.
PROJECT_ROOT = Path(__file__).resolve().parents[1]

DEFAULT_RAW = PROJECT_ROOT / "data" / "raw" / "prix-des-carburants-en-france-flux-instantane-v2.csv"
DEFAULT_PROCESSED = PROJECT_ROOT / "data" / "processed" / "carburants_clean.csv"


def save_processed(df: pd.DataFrame, dest: Path = DEFAULT_PROCESSED) -> Path:
    """
    Write the cleaned DataFrame to the processed data folder.

    Parameters:
    df (pd.DataFrame): The cleaned DataFrame.
    dest (Path): Where to write the CSV file.

    Returns:
    Path: The path to the written file.
    """
    dest = Path(dest)
    dest.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(
        dest,
        index=False,       # évite de créer une colonne parasite dans BigQuery
        encoding="utf-8",  # pas de BOM en sortie
        sep=",",           # standard pour l'ingestion BigQuery
    )
    return dest


# 10. POINT D'ENTREE

if __name__ == "__main__":
    df = validate(clean(load_raw(DEFAULT_RAW)))
    chemin = save_processed(df)
    print(f"{len(df)} lignes ecrites dans {chemin}")

