# Compilateur Français vers SQL

Ce projet contient un compilateur simple qui transforme des requêtes en français en commandes SQL basées sur le schéma suivant :

- `citoyens(id_citoyen PK, nom, prenom, adresse, telephone)`
- `vehicule(id_vehicule PK, immatriculation, modele, etat_vehicule, date_mise_service)`
- `capteur(id_capteur PK, type_capteur, localisation, date_installation, etat_capteur, id_mesure FK)`
- `mesure(id_mesure, valeur, unite, type_mesure, horodatage)`
- `intervention(id_intervention PK, date_demande, date_debut, date_fin, statut_intervention, id_capteur FK)`

## Hypothèse

Les attributs donnés avec des espaces dans l'énoncé ont été normalisés en SQL avec des underscores :

- `etat vehicule` devient `etat_vehicule`
- `date mise service` devient `date_mise_service`

## Utilisation

Lancer les tests :

```bash
python -m unittest -v
```

Afficher les conversions des exemples :

```bash
python sql_compiler.py
```

Compiler un prompt personnalisé :

```bash
python sql_compiler.py "Montre les mesures où valeur > 50 et type_mesure = 'pollution'"
```

## Base MySQL

Le schéma MySQL est disponible dans [schema_mysql.sql](schema_mysql.sql).

Créer la base et les tables :

```bash
mysql -u root -p < schema_mysql.sql
```

Cette commande supprime d'abord l'ancienne base `compcodex_db`, puis recrée le schéma complet.

Ce script crée la base `compcodex_db` avec :

- les 5 tables `citoyens`, `vehicule`, `capteur`, `mesure`, `intervention`
- les clés primaires et étrangères
- des index utiles pour les requêtes fréquentes du compilateur SQL
- des contraintes de domaine via `ENUM` pour `etat_capteur` et `etat_vehicule`

Remarque :

- dans ce schéma, `capteur.id_mesure` référence une mesure courante
- la table `mesure` ne contient pas de clé étrangère vers `capteur`
- `mesure.valeur` peut être `NULL` quand le capteur associé est `hors service`

Valeurs autorisées :

- `etat_capteur`: `inactif`, `actif`, `signale`, `en maintenance`, `hors service`
- `etat_vehicule`: `stationne`, `en route`, `en panne`, `arrive`

## Interface Streamlit

Installer les dépendances :

```bash
pip install -r requirements.txt
```

Lancer l'interface :

```bash
streamlit run streamlit_app.py
```

L'application permet de :

- visualiser toutes les tables MySQL
- insérer un jeu de données de base si la base est vide
- générer des données réalistes pour `mesure`
- mettre à jour `capteur.id_mesure` avec une mesure courante générée
- tester un prompt en français puis exécuter la requête SQL générée
- valider les automates de capteurs, interventions et véhicules
- générer des rapports IA avec actions recommandées à partir des données de la base

## Rapports IA

Le module `ai_reports.py` analyse les capteurs, mesures, zones polluées et interventions ouvertes. Il produit un rapport en français et une liste d'actions prioritaires.

Par défaut, le rapport utilise Hugging Face Inference Providers avec Llama 3.1 via l'endpoint compatible OpenAI Chat Completions. Le token peut être placé dans `.env` :

```bash
lama_apikey="hf_..."
```

Variables équivalentes supportées : `HF_TOKEN`, `HUGGINGFACEHUB_API_TOKEN` ou `AI_REPORT_API_KEY`. Le modèle par défaut est `meta-llama/Llama-3.1-8B-Instruct:novita` et la base URL par défaut est `https://router.huggingface.co/v1`. Si l'appel distant échoue ou si aucun token n'est configuré, l'application revient automatiquement au générateur local.
