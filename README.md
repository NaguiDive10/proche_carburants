# PRÉSENTATION DU PROJET

Dans un contexte de hausse des prix du carburant, les routiers recherchent de plus en plus des alternatives fiables pour réaliser autant d'économies que possible.

![flambée des prix](assets/ico/sign-emergency-code-sos_114_icon-icons.com_57210.svg)

La Data permet de répondre à ce type de problème concret. Ce projet s'inscrit dans un cadre d'analyse qui permet de comparer et de visualiser les prix du carburant dans les différentes régions françaises.

## Objectif

Aider les routiers à identifier les stations proches de leur localisation et à comparer les prix pour trouver le carburant le moins cher.

## Source

Les données utilisées sont strictement publiques et fiables. Elles sont issues du site du gouvernement [data.economie.gouv.fr](https://data.economie.gouv.fr/explore/dataset/prix-des-carburants-en-france-flux-instantane-v2/).

## Données en entrée / en sortie

### Entrée

Un fichier CSV de 47 colonnes séparées par `;`, environ 9 800 lignes, en encodage UTF-8.

### Sortie

Un fichier CSV au **format long (tidy)** : une ligne = une station × un carburant.

Seules les colonnes utiles sont conservées (mais pas non plus le strict minimum), et plus aucun JSON imbriqué.

| Contrainte | Imposée par | Conséquence sur le nettoyage |
|:-----------|:------------|:-----------------------------|
| Noms de colonnes snake_case, sans accent, sans espace, sans parenthèse | BigQuery | `Prix Gazole mis à jour le` → `gazole_maj` |
| Un type par colonne, stable | BigQuery | Le code postal doit rester STRING (sinon `01000` → `1000`) |
| Dates en TIMESTAMP/DATE réels | Looker Studio | Dates en ISO 8601 avec fuseau (`2026-09-28T13:45:27+02:00`) |
| Format long (tidy) plutôt que large | Looker Studio | Voir `to_long_format()`, c'est LA décision structurante |
| Pas de JSON imbriqué dans un CSV | BigQuery | 5 colonnes du fichier sont du JSON brut |

---

## Arborescence du projet

```text
Data analysis/
├─ data/
│  ├─ raw/           # intouchable, jamais modifié, jamais commité
│  │  └─ prix-des-carburants-en-france-flux-instantane-v2.csv
│  └─ processed/     # sorties générées, reproductibles
│     └─ carburants_clean.csv
├─ notebooks/
│  └─ 01_exploration.ipynb
├─ src/
│  └─ clean_carburants.py
├─ requirements.txt
└─ README.md
```

> Règle d'or : `data/raw/` est en lecture seule. Si le script casse, on relance depuis le brut.

### Rôle de chaque élément

| Élément | Rôle | Question à laquelle il répond |
|:--------|:-----|:------------------------------|
| `src/clean_carburants.py` | Toute la logique de transformation | « Comment nettoyer les données ? » |
| `notebooks/01_exploration.ipynb` | Exploration, visualisation, conclusions | « Que racontent les données ? » |
| `data/raw/` | Données originales, jamais modifiées | « D'où ça vient ? » |
| `data/processed/` | Données prêtes pour BigQuery / Looker Studio | « Qu'est-ce qu'on publie ? » |

---

## Démarche du projet

```text
                    DONNÉES BRUTES
                          │
                          ▼
                 Profilage / qualité
                          │
                          ▼
                Nettoyage / validation
                          │
                          ▼
                 ┌─────────────────┐
                 │  PRIX           │
                 │  carburants     │
                 └────────┬────────┘
                          │
          ┌───────────────┼────────────────┐
          ▼               ▼                ▼
       QUOI ?           OÙ ?            QUAND ?
     carburant        région/ville      évolution
          │               │                │
          ▼               ▼                ▼
     prix moyen        carte            tendance
     médiane           distance
     dispersion
          │               │                │
          └───────────────┴────────────────┘
                          ▼
                    ANALYSE MÉTIER
                          │
                          ▼
              « Où trouver le moins cher ? »
                          │
                          ▼
                     LOOKER STUDIO
```

---

## Pipeline de nettoyage

`src/clean_carburants.py` expose des fonctions unitaires, orchestrées par `clean()` puis contrôlées par `validate()` :

```text
clean_carburants.py
        │
        ├── load_raw()                 # lecture du CSV brut (séparateur ;, UTF-8)
        ├── normalize_column_names()   # snake_case, sans accent ni espace
        ├── fix_coordinates()          # latitude / longitude exploitables
        ├── cast_types()               # types stables (code postal en STRING, dates ISO)
        ├── to_long_format()           # passage large → long (1 ligne = station × carburant)
        ├── drop_invalid_prices()      # bornes de plausibilité (0,5 € – 5 €)
        ├── clean()                    # enchaîne les étapes ci-dessus
        └── validate()                 # garde-fous sur le résultat
                │
                ▼
            notebook
```

## Structure du notebook

```text
01_exploration.ipynb
│
├── 1. CONFIGURATION            imports, chemin RAW, chemin OUTPUT
├── 2. CHARGEMENT               load_raw() → df_raw
├── 3. EXPLORATION DU BRUT      shape, head, dtypes, manquants, doublons, stats
├── 4. PIPELINE DE NETTOYAGE    clean(df_raw) → df_clean
├── 5. VALIDATION               validate(df_clean)
├── 6. ANALYSE EXPLORATOIRE     carburants, géographie, temps, relations, métier
├── 7. CONCLUSIONS / INSIGHTS   observations, anomalies, recommandations
└── 8. EXPORT                   df_clean.to_csv() → data/processed/carburants_clean.csv
```

En version courte :

```text
CONFIGURATION → CHARGEMENT → EXPLORATION DU BRUT → NETTOYAGE
→ VALIDATION → ANALYSE / VISUALISATION → INSIGHTS → EXPORT
```

### Détail des analyses

**Partie 1 — Qualité des données**
1. Nombre de lignes / colonnes
2. Types
3. Valeurs manquantes
4. Doublons
5. Distribution des prix

**Partie 2 — Analyse descriptive**

6. Nombre de stations par carburant
7. Prix moyen / médian par carburant
8. Dispersion des prix par carburant

**Partie 3 — Analyse géographique**

9. Prix moyen par région
10. Top 10 des régions les plus chères
11. Carte des stations
12. Prix en fonction de la distance

**Partie 4 — Analyse des facteurs**

13. Population ↔ prix
14. Automate 24/24 ↔ prix

**Partie 5 — Analyse temporelle**

15. Évolution du prix selon les dates de mise à jour

**Partie 6 — Analyse métier**

16. Carburant le moins cher par ville
17. Stations les moins chères
18. Recherche de valeurs atypiques

---

## Installation

### Création de l'environnement d'exécution

À la racine du projet `Data analysis` :

1. `python -m venv .venv`
2. `.\.venv\Scripts\Activate.ps1`

### Installation des dépendances

`pip install -r requirements.txt`

### Utilisation

1. Placer le CSV source dans `data/raw/`.
2. Ouvrir `notebooks/01_exploration.ipynb` et exécuter les cellules dans l'ordre.
3. Le fichier nettoyé est écrit dans `data/processed/carburants_clean.csv`, prêt pour BigQuery puis Looker Studio.
