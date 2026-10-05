# Prix des carburants en France — pipeline d'analyse

Pipeline de préparation et d'analyse du **flux instantané des prix des carburants en France**, de la donnée brute publique jusqu'au tableau de bord géographique.

![Flambée des prix](assets/ico/sign-emergency-code-sos_114_icon-icons.com_57210.svg)

## Contexte

Dans un contexte de hausse durable des prix à la pompe, les routiers et les gros rouleurs cherchent des repères fiables pour arbitrer où faire le plein. L'information existe : elle est publiée en open data par le ministère de l'Économie. Elle est en revanche inexploitable en l'état — format large, JSON imbriqué, coordonnées encodées, prix aberrants.

Ce projet transforme ce flux en une table propre, typée et géolocalisée, puis l'exploite pour répondre à une question concrète : **quelle est la station la moins chère à proximité, et à quelle distance ?**

## Objectif

Permettre d'identifier les stations proches d'une position donnée et de comparer leurs prix, carburant par carburant, sur l'ensemble du territoire métropolitain.

## Source des données

Données publiques issues du site du ministère de l'Économie : [data.economie.gouv.fr — Prix des carburants en France, flux instantané v2](https://data.economie.gouv.fr/explore/dataset/prix-des-carburants-en-france-flux-instantane-v2/)

| | |
| :-- | :-- |
| Format | CSV, séparateur `;`, encodage UTF-8 |
| Volume | ~9 800 lignes × 47 colonnes |
| Granularité source | 1 ligne = 1 station, 1 colonne de prix par carburant |
| Fraîcheur | flux instantané, horodaté par carburant |

## Contrat de sortie

La cible n'est pas un CSV « propre » au sens général, mais un fichier directement ingérable par BigQuery et interrogeable depuis Looker Studio. Cinq contraintes en découlent :

| Contrainte | Imposée par | Conséquence sur le nettoyage |
| :-- | :-- | :-- |
| Noms de colonnes en `snake_case`, sans accent, espace ni parenthèse | BigQuery | `Prix Gazole mis à jour le` → `gazole_maj` |
| Un type par colonne, stable | BigQuery | le code postal reste `STRING` (sinon `01000` → `1000`) |
| Dates en `TIMESTAMP` réels | Looker Studio | conversion ISO 8601 → UTC |
| Format long (*tidy*) plutôt que large | Looker Studio | 1 ligne = 1 station × 1 carburant |
| Pas de JSON imbriqué dans le CSV | BigQuery | 5 colonnes de la source sont du JSON brut, écartées |

### Schéma produit

`data/processed/carburants_clean.csv` — ~31 000 lignes, 1 ligne par couple (station, carburant) :

| Colonne | Type | Remarque |
| :-- | :-- | :-- |
| `id` | STRING | identifiant de la station |
| `adresse`, `code_postal`, `ville` | STRING | `code_postal` conservé en texte |
| `departement`, `code_departement`, `region` | STRING | `code_departement` en texte (`2A`, `2B`) |
| `pop` | STRING | type d'implantation (route / autoroute) |
| `latitude`, `longitude` | FLOAT | degrés décimaux, arrondis à 5 décimales (~1 m) |
| `geom` | STRING | coordonnées brutes, conservées pour traçabilité |
| `automate_24_24_oui_non` | STRING | |
| `carburant_type` | STRING | `gazole`, `sp95`, `sp98`, `e10`, `e85`, `gplc` |
| `prix` | FLOAT | EUR/L |
| `maj` | TIMESTAMP | date de mise à jour du prix, en UTC |

## Traitements appliqués

Le pipeline est une séquence ordonnée de fonctions, chaînées via `DataFrame.pipe` dans [src/clean_carburants.py](src/clean_carburants.py) :

1. **`load_raw`** — lecture du CSV brut, sélection explicite des colonnes utiles, types forcés sur les identifiants. Aucune exception rattrapée : un plantage vaut mieux qu'un jeu de données silencieusement faux.
2. **`normalize_column_names`** — passage en `snake_case` sans accent, conforme à BigQuery.
3. **`fix_coordinates`** — extraction de la latitude et de la longitude depuis `geom`, qui contient déjà des degrés décimaux (les colonnes dédiées de la source sont en degrés × 10⁵).
4. **`cast_types`** — prix en numérique, dates en `TIMESTAMP` UTC. On stocke un instant absolu ; la conversion en heure locale se fait à l'affichage.
5. **`to_long_format`** — passage du format large au format long. La jointure se fait sur `(id, carburant)` seulement : joindre sur les colonnes d'identité ferait perdre les stations dont la ville ou la région est vide, une clé `NaN` ne s'appariant à aucune autre.
6. **`drop_invalid_prices`** — deux suppressions comptées séparément : prix absent (la station ne vend pas ce carburant) et prix hors plage (erreur de saisie). Les plages sont définies carburant par carburant — un seuil global laisserait passer un E85 à 2,20 €.
7. **`validate`** — contrôle du contrat de sortie : unicité de `(id, carburant)`, prix dans les plages, coordonnées en France métropolitaine, codes postaux à 5 caractères, aucune colonne vide. Les contrôles utilisent `raise` et non `assert`, qui serait désactivé par l'option `-O`.

## Arborescence

```text
Data analysis/
├─ assets/
│  └─ ico/              # illustrations
├─ data/
│  ├─ raw/              # instantané de référence, en lecture seule
│  └─ processed/        # sorties générées, reproductibles
├─ notebooks/
│  └─ 01_exploration.ipynb
├─ src/
│  ├─ download_raw.py   # récupère le flux depuis l'open data
│  └─ clean_carburants.py
├─ requirements.txt
└─ README.md
```

> **Règle d'or :** `data/raw/` est en lecture seule. Aucun traitement n'y écrit ; si le pipeline casse, on relance depuis le brut.

L'instantané de référence est versionné : un `git clone` suffit à obtenir un projet exécutable, sans appel réseau. Seul ce fichier est suivi — tout autre export déposé dans `data/raw/` est ignoré, afin que les rafraîchissements ne s'accumulent pas dans le dépôt.

## Installation

À la racine du projet :

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

## Exécution

Le dépôt est fourni avec un instantané du brut et le CSV nettoyé correspondant. Pour régénérer la sortie :

```powershell
python src/clean_carburants.py
```

Le script écrit `data/processed/carburants_clean.csv` et journalise le nombre de stations chargées, de lignes conservées et de lignes écartées par motif.

### Rafraîchir la donnée source

La source est un **flux instantané** : l'instantané versionné vieillit dès qu'il est commité. Pour le remplacer par un export à jour :

```powershell
python src/download_raw.py --force
python src/clean_carburants.py
```

`download_raw.py` interroge l'API d'export du portail avec les paramètres exacts attendus par le pipeline (libellés de colonnes, séparateur `;`, fuseau Europe/Paris). Trois garde-fous :

- sans `--force`, le script refuse d'écraser un brut existant ;
- l'écriture passe par un fichier `.part` renommé à la fin, donc une coupure réseau ne laisse jamais un brut tronqué à la place de la référence ;
- un export de moins de 10 Mo est rejeté — une réponse d'erreur renvoyée en `200` produirait sinon un CSV valide mais incomplet, que le nettoyage traiterait sans broncher.

---

## Suite du projet : BigQuery et Looker Studio

Le CSV nettoyé n'est pas la fin du pipeline, mais son point d'entrée dans l'entrepôt. L'analyse se poursuit en deux étapes.

### 1. Entreposage et requêtage dans BigQuery

La table est chargée dans BigQuery, où le schéma typé issu du nettoyage est repris tel quel :

```text
projet  : data-analytics-510421
dataset : fr_carburants
table   : fr_carburant
```

BigQuery apporte ici ce que pandas ne fait pas simplement : les **fonctions géospatiales natives**. La question métier du projet — *quelle est la station la moins chère à proximité* — devient une seule requête, sans calcul de distance à implémenter à la main.

Exemple : classement des stations vendant du SP95, du prix le plus bas au plus élevé, avec la distance à vol d'oiseau depuis une position donnée.

```sql
-- Distance entre une position (longitude 2.441013, latitude 48.639436)
-- et les stations proposant du SP95, classées par prix croissant.
SELECT
  carburant_type,
  prix,
  ROUND(
    ST_DISTANCE(
      ST_GEOGPOINT(longitude, latitude),
      ST_GEOGPOINT(2.441013116938259, 48.639436428704514)
    ) / 1000,
    2
  ) AS distance_km,
  adresse,
  ville,
  code_postal,
  region
FROM
  `data-analytics-510421.fr_carburants.fr_carburant`
WHERE
  carburant_type = 'sp95'
ORDER BY
  prix ASC,
  distance_km ASC
```

Points d'attention sur cette requête :

- `ST_GEOGPOINT` attend **la longitude en premier**, puis la latitude — l'inverse de l'ordre d'énoncé usuel.
- `ST_DISTANCE` renvoie des **mètres** sur le sphéroïde ; la division par 1 000 donne des kilomètres.
- Le tri secondaire est croissant (`ASC`) : à prix égal, on veut la station **la plus proche** en premier.
- C'est le format long qui rend le filtre `WHERE carburant_type = 'sp95'` possible. En format large, il aurait fallu viser une colonne différente par carburant.

### 2. Restitution dans Looker Studio

Looker Studio se branche sur la table BigQuery pour la couche de visualisation :

- **carte** des stations, colorée par niveau de prix ;
- **filtres** interactifs par carburant, région et département ;
- **séries temporelles** appuyées sur `maj`, converti à l'affichage dans le fuseau local ;
- **indicateurs** de prix minimum, moyen et médian par carburant et par territoire.

C'est cette chaîne complète — CSV public → nettoyage Python → BigQuery → Looker Studio — qui constitue le livrable du projet.

---

## Écart connu

Le CSV présent dans `data/processed/` expose les colonnes `adresse` et `carburant_type`, alors que la version actuelle de [src/clean_carburants.py](src/clean_carburants.py) produit `carburant` et n'inclut pas `adresse`. Le fichier a donc été généré par une version postérieure du script. À réaligner : ajouter `adresse` aux colonnes source et renommer `carburant` en `carburant_type`, afin que le script régénère exactement le schéma documenté ci-dessus et attendu par les requêtes BigQuery.
