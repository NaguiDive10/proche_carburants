import os
from pathlib import Path
import requests


# 1. SOURCE DISTANTE

# Export CSV de l'API Explore v2.1 de data.economie.gouv.fr.
# use_labels=true et delimiter=; reproduisent a l'identique le fichier
# telecharge manuellement depuis le portail : memes libelles de colonnes,
# meme ordre, meme separateur. load_raw() fonctionne donc sans modification.
EXPORT_URL = (
    "https://data.economie.gouv.fr/api/explore/v2.1/catalog/datasets/"
    "prix-des-carburants-en-france-flux-instantane-v2/exports/csv"
    "?delimiter=%3B&use_labels=true"
)

# Resolu depuis l'emplacement de ce fichier (voir clean_carburants.py).
PROJECT_ROOT = Path(__file__).resolve().parents[1]

DEFAULT_DEST = PROJECT_ROOT / "data" / "raw" / "prix-des-carburants-en-france-flux-instantane-v2.csv"


# 2. TELECHARGEMENT

def fetch_raw(dest: Path = DEFAULT_DEST, url: str = EXPORT_URL, timeout: int = 180) -> Path:
    """
    Download the instantaneous fuel price feed into the raw data folder.

    The response is streamed to a temporary ".part" file, then moved onto the
    destination only once the download succeeded: a network failure can never
    leave a truncated file in place of the previous raw dataset.

    Parameters:
    dest (Path): Where to write the CSV file.
    url (str): The export endpoint to download from.
    timeout (int): Seconds to wait for the server to respond.

    Returns:
    Path: The path to the downloaded file.
    """
    dest = Path(dest)
    dest.parent.mkdir(parents=True, exist_ok=True)
    tmp = dest.with_suffix(dest.suffix + ".part")

    try:
        with requests.get(url, stream=True, timeout=timeout) as response:
            response.raise_for_status()
            with open(tmp, "wb") as file:
                for chunk in response.iter_content(chunk_size=1 << 16):
                    file.write(chunk)
    except requests.RequestException as e:
        tmp.unlink(missing_ok=True)
        raise RuntimeError(f"Echec du telechargement depuis {url} : {e}") from e

    os.replace(tmp, dest)

    return dest


# 3. POINT D'ENTREE

# __name__ == "__main__" pour n'executer que la fonction que si ce fichier est lancé et non pas à l'import du module. 
# importer le module ne doit pas declencher un telechargement de 19,5 Mo.
# (python src/fetch_carburants.py)
if __name__ == "__main__":
    chemin = fetch_raw()
    print(f"Flux telecharge : {chemin} ({chemin.stat().st_size / 1e6:.1f} Mo)")
