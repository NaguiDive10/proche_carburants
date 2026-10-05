"""Telechargement du flux instantane des prix des carburants en France.

Recupere le CSV source depuis l'API publique de data.economie.gouv.fr et
l'ecrit dans data/raw/. Le depot contient deja un instantane committe, afin
qu'un clone suffise a faire tourner le pipeline ; ce script sert a le
rafraichir, la source etant un flux mis a jour en continu.

Usage :
    python src/download_raw.py           # refuse d'ecraser un fichier existant
    python src/download_raw.py --force   # remplace l'instantane en place
"""

# 1. IMPORTS
import argparse
import os
from pathlib import Path

import requests


# 2. CONSTANTES

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "data" / "raw" / "prix-des-carburants-en-france-flux-instantane-v2.csv"

# Endpoint d'export du portail (Opendatasoft v2.1). Les parametres ne sont pas
# cosmetiques : ils reproduisent exactement le format attendu par
# clean_carburants.py, dont les noms de colonnes sont ecrits en dur.
#   use_labels=true -> en-tetes libelles ("Prix Gazole") et non techniques
#   delimiter=;     -> separateur attendu par load_raw()
#   timezone        -> dates en ISO 8601 avec le fuseau de Paris
URL = (
    "https://data.economie.gouv.fr/api/explore/v2.1/catalog/datasets"
    "/prix-des-carburants-en-france-flux-instantane-v2/exports/csv"
)
PARAMS = {
    "lang": "fr",
    "timezone": "Europe/Paris",
    "use_labels": "true",
    "delimiter": ";",
}

# Un export complet pese environ 19 Mo et le portail peut mettre plusieurs
# dizaines de secondes a le generer avant d'emettre le premier octet.
TIMEOUT = (10, 180)  # (connexion, lecture)
CHUNK = 1 << 16  # 64 Kio
PALIER = 2 * 1024 * 1024  # frequence d'affichage de la progression

# Garde-fou de volume : un export ampute (coupure reseau, erreur serveur
# renvoyee en 200) donnerait un CSV syntaxiquement valide mais incomplet, que
# le pipeline nettoierait sans broncher.
TAILLE_MINIMALE = 10 * 1024 * 1024


# 3. TELECHARGEMENT
def download(path: Path = OUT, force: bool = False) -> Path:
    """
    Download the raw CSV from the open data portal.

    L'ecriture passe par un fichier temporaire renomme en fin de course. Un
    telechargement interrompu laisserait sinon un brut tronque a la place de
    l'instantane de reference, en violation de la regle du projet : data/raw/
    doit toujours etre une source sur laquelle on peut relancer le pipeline.

    Parameters:
    path (Path): Destination of the downloaded file.
    force (bool): Overwrite the file if it already exists.

    Returns:
    Path: The path actually written.
    """
    if path.exists() and not force:
        raise FileExistsError(
            f"{path.name} existe deja. Relancez avec --force pour le remplacer."
        )

    path.parent.mkdir(parents=True, exist_ok=True)
    temporaire = path.with_suffix(path.suffix + ".part")

    print(f"[1/3] requete  : {URL}")
    with requests.get(URL, params=PARAMS, stream=True, timeout=TIMEOUT) as reponse:
        reponse.raise_for_status()

        octets = 0
        palier_suivant = PALIER
        with temporaire.open("wb") as sortie:
            for morceau in reponse.iter_content(chunk_size=CHUNK):
                sortie.write(morceau)
                octets += len(morceau)

                # On n'affiche qu'au franchissement d'un palier : le retour
                # chariot n'est pas interprete quand la sortie est redirigee
                # vers un fichier, ou chaque morceau laisserait une ligne.
                if octets >= palier_suivant:
                    print(f"\r[2/3] recu     : {octets / 1e6:>6.1f} Mo", end="")
                    palier_suivant += PALIER
        print(f"\r[2/3] recu     : {octets / 1e6:>6.1f} Mo")

    if octets < TAILLE_MINIMALE:
        temporaire.unlink(missing_ok=True)
        raise OSError(
            f"Export suspect : {octets / 1e6:.1f} Mo recus, "
            f"au moins {TAILLE_MINIMALE / 1e6:.0f} Mo attendus."
        )

    # os.replace est atomique et ecrase la cible, contrairement a Path.rename
    # qui echoue sous Windows si le fichier de destination existe.
    os.replace(temporaire, path)
    print(f"[3/3] ecrit    : {path}")

    return path


# 4. POINT D'ENTREE
if __name__ == "__main__":
    analyseur = argparse.ArgumentParser(
        description="Telecharge le flux instantane des prix des carburants."
    )
    analyseur.add_argument(
        "--force",
        action="store_true",
        help="remplace le fichier brut existant",
    )
    arguments = analyseur.parse_args()

    download(force=arguments.force)
