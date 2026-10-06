# PRÉSENTATION DU PROJET

Dans un contexte de hausse des prix du carburant, les routiers recherchent de plus en plus des altenartifs fiables pour réaliser autant d'économie que possible.

![flambée des prix](assets\ico\sign-emergency-code-sos_114_icon-icons.com_57210.svg)

Conscient que la Data permet de résoudre des problèmes en apportant des solutions des plus fiables, ce projet ne fait pas exception. Il s'inscrit dans un cadre d'analyse qui permet de visualiser les prix du carburant dans différentes régions.

## Objectif

Aider les routiers à identifier les stations à carburants proches de leur localisation et de comparer les prix les plus moins chers.

## Source

Les données utilisées dans ce projet sont strictecment publiques et fiables. Issues du site du gouvenement [data.economie.gouv.fr](https://data.economie.gouv.fr/explore/assets/prix-des-carburants-en-france-flux-instantane-v2/)

## Donées en entrée/en sortie

### Entrée

Le fichier est en format CSV de 47 colonnes séparées par `;` , 9 800 lignes et en encodage UTF-8.

### Sortie

Le format attendu est le CSV.

Seules les colonnes utiles seront gardées (mais pas non plus le strict minimum).

Pas de JSON imbriqué dans le CSV.


|contrainte |Imposée par |Conséquence sur le nettoyage|
|:-----------|:------------|:-----------------------------|
|Noms de colonnes snake_case, sans accent, sans espace, sans parenthèse|	BigQuery	|Prix Gazole mis à jour le → gazole_maj|
|Un type par colonne, stable|	BigQuery	|Code postal doit rester STRING (sinon 01000 → 1000)|
|Dates en TIMESTAMP/DATE réels|	Looker Studio	|les dates sont en ISO 8601 avec fuseau (2026-09-28T13:45:27+02:00)|
|Format long (tidy) plutôt que large	|Looker Studio|	voir étape 4, c'est LA décision structurante|
|Pas de JSON imbriqué dans un CSV	|BigQuery	|5 colonnes du fichier sont du JSON brut|

---

## Arborescence du projet

```Text
Data analysis/
├─ data/
│  ├─ raw/          # intouchable, jamais modifié, jamais commité
│  └─ processed/     # sorties générées, reproductibles
├─ notebooks/
│  └─ 01_exploration.ipynb
├─ src/
│  └─ clean_carburants.py
├─ requirements.txt
└─ README.md
```

> Règle d'or : data/raw/ est en lecture seule. Si le script casse, on relance depuis le brut.

### Création de l'environement d'exécution du code

à la racine du projet Data analysis:
1. `python -m venv .venv`
2. `.\.venv\Scripts\Activate.ps1`

### Installation des dépendances
`pip install -r requirements.txt`