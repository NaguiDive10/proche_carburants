"""Nettoyage du flux instantané des prix des carburants en France.

Transforme le CSV brut de data.economie.gouv.fr en une table longue
(une ligne = une station x un carburant) prête pour BigQuery.

Usage :
    python src/clean_carburants.py
"""

# 1. IMPORTS
import re
import unicodedata
from pathlib import Path

import pandas as pd


# 2. CONSTANTES

# Path(__file__) = ce fichier ; parents[1] = la racine du projet.
# Un chemin relatif comme "../data" dépendrait du dossier courant.
ROOT = Path(__file__).resolve().parents[1]
RAW = ROOT / "data" / "raw" / "prix-des-carburants-en-france-flux-instantane-v2.csv"
OUT = ROOT / "data" / "processed" / "carburants_clean.csv"

CARBURANTS = ["gazole", "sp95", "sp98", "e10", "e85", "gplc"]

# Colonnes du fichier source. Les noms de prix et de dates sont dérivés plutôt
# que recopiés : impossible d'en oublier un ou d'en dupliquer un.
COL_IDENTITE = [
    "id",
    "Code postal",
    "Ville",
    "Département",
    "code_departement",
    "Région",
]
COL_CONTEXTE = ["pop", "geom", "Automate 24-24 (oui/non)"]
COL_PRIX = ["Prix Gazole", "Prix SP95", "Prix SP98", "Prix E10", "Prix E85", "Prix GPLc"]
COL_MAJ = [f"{c} mis à jour le" for c in COL_PRIX]

COLONNES_SOURCE = COL_IDENTITE + COL_CONTEXTE + COL_PRIX + COL_MAJ

# Codes à garder en texte : zéros initiaux (05100) et codes corses (2A, 2B).
DTYPES_SOURCE = {
    "id": "string",
    "Code postal": "string",
    "code_departement": "string",
}

# Colonnes conservées comme identifiants lors du passage au format long,
# après normalisation des noms.
COL_ID_LONG = [
    "id",
    "code_postal",
    "ville",
    "departement",
    "code_departement",
    "region",
    "pop",
    "latitude",
    "longitude",
    "geom",
    "automate_24_24_oui_non",
]

# Plages de prix plausibles en EUR/L, carburant par carburant.
# Un seuil global ne détecte rien : un E85 à 2,20 EUR passerait un test
# "entre 0,5 et 5" alors qu'il s'agit d'une erreur de saisie du gérant.
PLAGES_PRIX = {
    "gazole": (1.00, 3.00),
    "sp95": (1.00, 3.00),
    "sp98": (1.00, 3.00),
    "e10": (1.00, 3.00),
    "e85": (0.50, 1.50),
    "gplc": (0.50, 1.50),
}


# 3. FONCTIONS DU PIPELINE
def load_raw(path: Path = RAW) -> pd.DataFrame:
    """
    Load the raw data from a CSV file into a pandas DataFrame.

    Aucune exception n'est rattrapée : si le fichier est absent, si une colonne
    a disparu ou si le séparateur change, le script doit s'arrêter net. Un
    plantage vaut mieux qu'un DataFrame silencieusement faux, qui propagerait
    l'erreur jusqu'au tableau de bord.

    Parameters:
    path (Path): The path to the CSV file.

    Returns:
    pd.DataFrame: The loaded DataFrame.
    """
    if not path.is_file():
        raise FileNotFoundError(f"Fichier source introuvable : {path}")

    return pd.read_csv(
        path,
        sep=";",
        encoding="utf-8-sig",
        usecols=COLONNES_SOURCE,
        dtype=DTYPES_SOURCE,
        decimal=".",
    )


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
    df = df.copy()

    def normalize(col: str) -> str:
        # Remove accents
        col = unicodedata.normalize("NFKD", col).encode("ascii", "ignore").decode("utf-8")

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


def fix_coordinates(df: pd.DataFrame) -> pd.DataFrame:
    """
    Extract latitude and longitude from the geom column.

    La colonne geom contient déjà les degrés décimaux ("48.183, 3.309"), alors
    que les colonnes latitude/longitude du flux sont exprimées en degrés
    multipliés par 10**5. Partir de geom évite donc la conversion.

    L'arrondi à 5 décimales (environ 1 m) harmonise la précision : la source
    fournit un nombre de chiffres variable (48.183 à côté de 47.257413021458).

    Parameters:
    df (pd.DataFrame): The DataFrame containing the geom column.

    Returns:
    pd.DataFrame: The DataFrame with latitude and longitude columns.
    """
    df = df.copy()

    coordinates = df["geom"].str.split(",", expand=True)

    df["latitude"] = pd.to_numeric(coordinates[0], errors="coerce").round(5)
    df["longitude"] = pd.to_numeric(coordinates[1], errors="coerce").round(5)

    return df


def cast_types(df: pd.DataFrame) -> pd.DataFrame:
    """
    Cast the price and date columns to their proper types.

    Les dates sont converties en UTC : on stocke un instant absolu et on
    convertit au fuseau local à l'affichage, dans Looker Studio.

    Parameters:
    df (pd.DataFrame): The DataFrame whose column types are to be cast.

    Returns:
    pd.DataFrame: The DataFrame with casted column types.
    """
    df = df.copy()

    for carburant in CARBURANTS:
        df[f"prix_{carburant}"] = pd.to_numeric(
            df[f"prix_{carburant}"], errors="coerce"
        )
        df[f"{carburant}_maj"] = pd.to_datetime(
            df[f"prix_{carburant}_mis_a_jour_le"], errors="coerce", utc=True
        )

    return df


def to_long_format(df: pd.DataFrame) -> pd.DataFrame:
    """
    Convert the DataFrame from wide format to long format.

    Entrée : une ligne par station, 6 colonnes de prix et 6 colonnes de date.
    Sortie : une ligne par (station, carburant), avec les colonnes carburant,
    prix et maj.

    La jointure des deux melt se fait sur (id, carburant) uniquement. Joindre
    sur les 11 colonnes d'identité ferait perdre les 5 stations dont la ville,
    le département et la région sont vides : dans une jointure pandas, une clé
    NaN ne correspond à aucune autre, pas même à une autre NaN.

    Parameters:
    df (pd.DataFrame): The DataFrame in wide format.

    Returns:
    pd.DataFrame: The DataFrame in long format with 'carburant' and 'prix'.
    """
    df = df.copy()

    col_prix = [f"prix_{c}" for c in CARBURANTS]
    col_maj = [f"{c}_maj" for c in CARBURANTS]

    df_prix = df.melt(
        id_vars=COL_ID_LONG,
        value_vars=col_prix,
        var_name="carburant",
        value_name="prix",
    )
    df_prix["carburant"] = df_prix["carburant"].str.removeprefix("prix_")

    df_maj = df.melt(
        id_vars=["id"],
        value_vars=col_maj,
        var_name="carburant",
        value_name="maj",
    )
    df_maj["carburant"] = df_maj["carburant"].str.removesuffix("_maj")

    return df_prix.merge(df_maj, on=["id", "carburant"], how="left")


def drop_invalid_prices(df: pd.DataFrame) -> pd.DataFrame:
    """
    Drop rows with no price, then rows whose price is out of range.

    Les deux suppressions sont distinctes et comptées séparément :
    - un prix absent signifie que la station ne vend pas ce carburant ;
    - un prix hors plage est une erreur de saisie.
    Les confondre masquerait un problème de qualité derrière un cas normal.

    Parameters:
    df (pd.DataFrame): The DataFrame in long format.

    Returns:
    pd.DataFrame: The filtered DataFrame.
    """
    df = df.copy()

    avant = len(df)
    df = df.dropna(subset=["prix"])
    sans_prix = avant - len(df)

    mini = df["carburant"].map(lambda c: PLAGES_PRIX[c][0])
    maxi = df["carburant"].map(lambda c: PLAGES_PRIX[c][1])
    plausible = df["prix"].between(mini, maxi)

    print(f"      {sans_prix:>5} lignes sans prix (carburant non vendu)")
    print(f"      {(~plausible).sum():>5} prix hors plage (erreur de saisie)")

    return df[plausible].copy()


def validate(df: pd.DataFrame) -> pd.DataFrame:
    """
    Check the output contract and raise if it is violated.

    On utilise raise et non assert : les assertions disparaissent lorsque
    Python est lancé avec l'option -O, et un contrôle qualité ne doit jamais
    pouvoir être désactivé par accident.

    Parameters:
    df (pd.DataFrame): The DataFrame to check.

    Returns:
    pd.DataFrame: The same DataFrame, unchanged.
    """
    if df.duplicated(["id", "carburant"]).any():
        raise ValueError("Doublons détectés sur la paire (id, carburant)")

    for carburant, (lo, hi) in PLAGES_PRIX.items():
        prix = df.loc[df["carburant"] == carburant, "prix"]
        if not prix.between(lo, hi).all():
            raise ValueError(f"{carburant} : prix hors de [{lo}, {hi}]")

    if not df["latitude"].between(41, 52).all():
        raise ValueError("Latitude hors France métropolitaine")

    if not df["longitude"].between(-6, 10).all():
        raise ValueError("Longitude hors France métropolitaine")

    if (df["code_postal"].str.len() != 5).any():
        raise ValueError("Code postal de longueur différente de 5")

    vides = df.columns[df.isna().all()].tolist()
    if vides:
        raise ValueError(f"Colonnes entièrement vides : {vides}")

    return df


# 4. ORCHESTRATION
def clean(df: pd.DataFrame) -> pd.DataFrame:
    """
    Apply the cleaning functions in order.

    L'ordre n'est pas libre : normalize_column_names doit passer en premier
    (toutes les fonctions suivantes utilisent les noms normalisés), et validate
    en dernier, sur la table telle qu'elle sera exportée.
    """
    return (
        df.pipe(normalize_column_names)
        .pipe(fix_coordinates)
        .pipe(cast_types)
        .pipe(to_long_format)
        .pipe(drop_invalid_prices)
        .pipe(validate)
    )


# 5. POINT D'ENTRÉE
if __name__ == "__main__":
    brut = load_raw()
    print(f"[1/3] chargé  : {len(brut):>6} stations, {brut.shape[1]} colonnes")

    propre = clean(brut)
    print(f"[2/3] nettoyé : {len(propre):>6} lignes, {propre['id'].nunique()} stations")

    OUT.parent.mkdir(parents=True, exist_ok=True)
    propre.to_csv(OUT, index=False, encoding="utf-8")
    print(f"[3/3] écrit   : {OUT}")
