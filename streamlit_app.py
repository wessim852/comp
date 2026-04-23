from __future__ import annotations

import random
from contextlib import closing
from dataclasses import dataclass
from datetime import datetime, timedelta

import mysql.connector
import pandas as pd
import streamlit as st
from mysql.connector import Error

from sql_compiler import FrenchSQLCompiler


APP_TITLE = "CompCodex MySQL Console"
DATABASE_NAME = "compcodex_db"
CAPTEUR_ETATS = ["incatif", "actif", "signale", "en maintenance", "hors service"]
VEHICULE_ETATS = ["stationne", "en route", "en panne", "arrive"]
TABLES = ["citoyens", "vehicule", "capteur", "mesure", "intervention"]


@dataclass(frozen=True)
class ConnectionSettings:
    host: str
    port: int
    user: str
    password: str
    database: str


def get_connection(settings: ConnectionSettings):
    return mysql.connector.connect(
        host=settings.host,
        port=settings.port,
        user=settings.user,
        password=settings.password,
        database=settings.database,
    )


def run_select(settings: ConnectionSettings, query: str, params: tuple | None = None) -> pd.DataFrame:
    with closing(get_connection(settings)) as connection:
        cursor = connection.cursor(dictionary=True)
        cursor.execute(query, params or ())
        rows = cursor.fetchall()
        return pd.DataFrame(rows)


def run_statement(
    settings: ConnectionSettings,
    query: str,
    params: tuple | list[tuple] | None = None,
    many: bool = False,
) -> int:
    with closing(get_connection(settings)) as connection:
        cursor = connection.cursor()
        if many:
            cursor.executemany(query, params or [])
        else:
            cursor.execute(query, params or ())
        connection.commit()
        return cursor.rowcount


def table_count(settings: ConnectionSettings, table_name: str) -> int:
    with closing(get_connection(settings)) as connection:
        cursor = connection.cursor()
        cursor.execute(f"SELECT COUNT(*) FROM {table_name}")
        return int(cursor.fetchone()[0])


def fetch_ids(settings: ConnectionSettings, table_name: str, id_column: str) -> list[int]:
    with closing(get_connection(settings)) as connection:
        cursor = connection.cursor()
        cursor.execute(f"SELECT {id_column} FROM {table_name} ORDER BY {id_column}")
        return [row[0] for row in cursor.fetchall()]


def fetch_capteur_rows(settings: ConnectionSettings) -> list[tuple[int, str, str]]:
    with closing(get_connection(settings)) as connection:
        cursor = connection.cursor()
        cursor.execute(
            "SELECT id_capteur, type_capteur, etat_capteur FROM capteur ORDER BY id_capteur"
        )
        return cursor.fetchall()


def insert_measure_rows(
    settings: ConnectionSettings,
    rows: list[tuple[float, str, str, datetime | str]],
) -> list[int]:
    inserted_ids: list[int] = []
    with closing(get_connection(settings)) as connection:
        cursor = connection.cursor()
        for row in rows:
            cursor.execute(
                "INSERT INTO mesure (valeur, unite, type_mesure, horodatage) VALUES (%s, %s, %s, %s)",
                row,
            )
            inserted_ids.append(int(cursor.lastrowid))
        connection.commit()
    return inserted_ids


def update_capteur_current_measures(
    settings: ConnectionSettings,
    links: list[tuple[int, int]],
) -> int:
    return run_statement(
        settings,
        "UPDATE capteur SET id_mesure = %s WHERE id_capteur = %s",
        [(measure_id, capteur_id) for capteur_id, measure_id in links],
        many=True,
    )


def seed_reference_data(settings: ConnectionSettings) -> dict[str, int]:
    inserted: dict[str, int] = {}

    citizens = [
        ("Ben Salem", "Amine", "Tunis", "20112233"),
        ("Trabelsi", "Sarra", "Sousse", "22114455"),
        ("Mansouri", "Youssef", "Sfax", "24112233"),
        ("Jaziri", "Meriem", "Nabeul", "28110022"),
        ("Gharbi", "Khalil", "Monastir", "29113344"),
    ]
    vehicles = [
        ("TU-2401", "Renault Kangoo", "stationne", "2022-03-15"),
        ("TU-2402", "Peugeot Partner", "en route", "2021-09-10"),
        ("TU-2403", "Citroen Berlingo", "arrive", "2023-01-20"),
        ("TU-2404", "Fiat Doblo", "en panne", "2020-07-05"),
    ]
    measures = [
        (78.4, "AQI", "pollution", "2026-04-23 08:00:00"),
        (26.1, "C", "temperature", "2026-04-23 08:00:00"),
        (63.5, "%", "humidite", "2026-04-23 08:00:00"),
        (72.8, "dB", "bruit", "2026-04-23 08:00:00"),
        (95.2, "AQI", "pollution", "2026-04-23 09:30:00"),
        (54.7, "AQI", "pollution", "2026-04-23 10:00:00"),
    ]
    if table_count(settings, "citoyens") == 0:
        inserted["citoyens"] = run_statement(
            settings,
            "INSERT INTO citoyens (nom, prenom, adresse, telephone) VALUES (%s, %s, %s, %s)",
            citizens,
            many=True,
        )
    else:
        inserted["citoyens"] = 0

    if table_count(settings, "vehicule") == 0:
        inserted["vehicule"] = run_statement(
            settings,
            "INSERT INTO vehicule (immatriculation, modele, etat_vehicule, date_mise_service) VALUES (%s, %s, %s, %s)",
            vehicles,
            many=True,
        )
    else:
        inserted["vehicule"] = 0

    existing_measure_ids = fetch_ids(settings, "mesure", "id_mesure")
    if len(existing_measure_ids) < 6:
        missing_count = 6 - len(existing_measure_ids)
        inserted_measure_ids = insert_measure_rows(settings, measures[:missing_count])
        inserted["mesure"] = len(inserted_measure_ids)
        measure_ids = existing_measure_ids + inserted_measure_ids
    else:
        inserted["mesure"] = 0
        measure_ids = existing_measure_ids

    if table_count(settings, "capteur") == 0:
        if len(measure_ids) < 6:
            raise ValueError("Impossible de générer les capteurs: il faut au moins 6 mesures.")
        sensors = [
            ("pollution", "Centre Ville Tunis", "2024-01-11", "actif", measure_ids[0]),
            ("temperature", "Lac 1 Tunis", "2024-02-18", "actif", measure_ids[1]),
            ("humidite", "Sousse Corniche", "2024-03-04", "signale", measure_ids[2]),
            ("bruit", "Sfax Medina", "2024-03-22", "en maintenance", measure_ids[3]),
            ("pollution", "Monastir Centre", "2024-04-12", "hors service", measure_ids[4]),
            ("pollution", "Nabeul Plage", "2024-04-26", "incatif", measure_ids[5]),
        ]
        inserted["capteur"] = run_statement(
            settings,
            "INSERT INTO capteur (type_capteur, localisation, date_installation, etat_capteur, id_mesure) VALUES (%s, %s, %s, %s, %s)",
            sensors,
            many=True,
        )
    else:
        inserted["capteur"] = 0

    if table_count(settings, "intervention") == 0:
        sensor_ids = fetch_ids(settings, "capteur", "id_capteur")
        if len(sensor_ids) < 5:
            raise ValueError("Impossible de générer les interventions: données de référence insuffisantes.")
        interventions = [
            ("2026-04-20 09:00:00", "2026-04-20 10:30:00", None, "en_cours", sensor_ids[2]),
            ("2026-04-18 08:15:00", "2026-04-18 09:00:00", "2026-04-18 12:30:00", "terminee", sensor_ids[3]),
            ("2026-04-19 11:00:00", None, None, "demande", sensor_ids[4]),
        ]
        inserted["intervention"] = run_statement(
            settings,
            "INSERT INTO intervention (date_demande, date_debut, date_fin, statut_intervention, id_capteur) VALUES (%s, %s, %s, %s, %s)",
            interventions,
            many=True,
        )
    else:
        inserted["intervention"] = 0

    return inserted


def sensor_measure_profile(sensor_type: str) -> tuple[str, float, float]:
    profiles = {
        "pollution": ("AQI", 35.0, 120.0),
        "temperature": ("C", 14.0, 39.0),
        "humidite": ("%", 35.0, 92.0),
        "bruit": ("dB", 38.0, 95.0),
    }
    return profiles.get(sensor_type, ("unite", 0.0, 100.0))


def generate_measure_rows(
    sensor_records: list[tuple[int, str, str]],
    per_sensor: int,
    step_minutes: int,
) -> tuple[list[tuple[float, str, str, datetime]], list[tuple[int, int]]]:
    rows: list[tuple[float, str, str, datetime]] = []
    current_links: list[tuple[int, int]] = []
    now = datetime.now().replace(second=0, microsecond=0)

    for sensor_id, sensor_type, sensor_state in sensor_records:
        if sensor_state == "hors service":
            continue
        unit, low, high = sensor_measure_profile(sensor_type)
        anchor = random.uniform(low, high)
        last_generated_index = -1
        for offset in range(per_sensor):
            timestamp = now - timedelta(minutes=offset * step_minutes)
            drift = random.uniform(-6.0, 6.0)
            if sensor_type == "pollution":
                hour_boost = 18 if 7 <= timestamp.hour <= 9 or 17 <= timestamp.hour <= 20 else 0
                value = max(low, min(high + 40, anchor + drift + hour_boost))
            elif sensor_type == "temperature":
                daytime = 8 if 11 <= timestamp.hour <= 16 else -3
                value = max(low, min(high, anchor + drift + daytime))
            elif sensor_type == "humidite":
                value = max(low, min(high, anchor + drift + random.uniform(3.0, 10.0)))
            elif sensor_type == "bruit":
                rush = 10 if 8 <= timestamp.hour <= 18 else -8
                value = max(low, min(high, anchor + drift + rush))
            else:
                value = max(low, min(high, anchor + drift))
            rows.append((round(value, 2), unit, sensor_type, timestamp))
            if offset == 0:
                last_generated_index = len(rows) - 1
        if last_generated_index >= 0:
            current_links.append((sensor_id, last_generated_index))
    return rows, current_links


def insert_generated_measures(settings: ConnectionSettings, per_sensor: int, step_minutes: int) -> int:
    sensor_records = fetch_capteur_rows(settings)
    rows, current_links = generate_measure_rows(sensor_records, per_sensor, step_minutes)
    if not rows:
        return 0

    inserted_measure_ids = insert_measure_rows(settings, rows)
    capteur_measure_links = [
        (capteur_id, inserted_measure_ids[row_index])
        for capteur_id, row_index in current_links
    ]
    if capteur_measure_links:
        update_capteur_current_measures(settings, capteur_measure_links)
    return len(inserted_measure_ids)


def load_table_preview(settings: ConnectionSettings, table_name: str, limit: int) -> pd.DataFrame:
    return run_select(settings, f"SELECT * FROM {table_name} ORDER BY 1 DESC LIMIT {limit}")


def load_stats(settings: ConnectionSettings) -> pd.DataFrame:
    query = """
        SELECT
            c.localisation,
            m.type_mesure,
            ROUND(m.valeur, 2) AS valeur_courante,
            m.horodatage
        FROM capteur c
        JOIN mesure m ON c.id_mesure = m.id_mesure
        ORDER BY m.horodatage DESC, m.valeur DESC
        LIMIT 20
    """
    return run_select(settings, query)


def build_sidebar() -> ConnectionSettings:
    st.sidebar.header("Connexion MySQL")
    host = st.sidebar.text_input("Host", value="localhost")
    port = st.sidebar.number_input("Port", min_value=1, max_value=65535, value=3306)
    user = st.sidebar.text_input("User", value="root")
    password = st.sidebar.text_input("Password", type="password")
    database = st.sidebar.text_input("Database", value=DATABASE_NAME)

    st.sidebar.divider()
    st.sidebar.caption("Valeurs autorisées")
    st.sidebar.write(f"`etat_capteur`: {', '.join(CAPTEUR_ETATS)}")
    st.sidebar.write(f"`etat_vehicule`: {', '.join(VEHICULE_ETATS)}")

    return ConnectionSettings(
        host=host,
        port=int(port),
        user=user,
        password=password,
        database=database,
    )


def main() -> None:
    st.set_page_config(page_title=APP_TITLE, layout="wide")
    st.title(APP_TITLE)
    st.caption("Visualiser les tables MySQL, générer des données réalistes et tester le compilateur NL → SQL.")

    settings = build_sidebar()
    compiler = FrenchSQLCompiler()

    try:
        counts = {table: table_count(settings, table) for table in TABLES}
    except Error as exc:
        st.error(f"Connexion MySQL impossible: {exc}")
        st.info("Assure-toi d'avoir exécuté `mysql -u root -p < schema_mysql.sql` avant d'ouvrir l'application.")
        return

    metrics = st.columns(len(TABLES))
    for index, table in enumerate(TABLES):
        metrics[index].metric(table, counts[table])

    tab_data, tab_seed, tab_nl = st.tabs(["Tables", "Génération", "NL → SQL"])

    with tab_data:
        left, right = st.columns([1, 2])
        with left:
            selected_table = st.selectbox("Table", TABLES)
            preview_limit = st.slider("Nombre de lignes", min_value=5, max_value=200, value=25, step=5)
        with right:
            preview = load_table_preview(settings, selected_table, preview_limit)
            st.dataframe(preview, use_container_width=True, height=520)

        if counts["mesure"] > 0:
            st.subheader("Aperçu analytique des mesures")
            st.dataframe(load_stats(settings), use_container_width=True, height=320)

    with tab_seed:
        st.subheader("Jeu de données de démonstration")
        st.write("1. Insère citoyens, véhicules, capteurs et interventions si les tables sont vides.")
        if st.button("Insérer les données de base", use_container_width=True):
            try:
                inserted = seed_reference_data(settings)
                st.success(
                    "Insertion terminée: "
                    + ", ".join(f"{table}={count}" for table, count in inserted.items())
                )
            except Exception as exc:  # noqa: BLE001
                st.error(f"Insertion impossible: {exc}")

        st.divider()
        st.subheader("Génération réaliste de mesures")
        per_sensor = st.slider("Mesures par capteur", min_value=12, max_value=720, value=48, step=12)
        step_minutes = st.select_slider("Intervalle temporel", options=[5, 10, 15, 30, 60], value=30)
        st.caption("Les capteurs `hors service` ne génèrent pas de mesures. Le schéma relie chaque capteur à une mesure courante via `id_mesure`.")

        if st.button("Générer des mesures", type="primary", use_container_width=True):
            try:
                inserted_rows = insert_generated_measures(settings, per_sensor, step_minutes)
                if inserted_rows == 0:
                    st.warning("Aucun capteur exploitable trouvé. Insère d'abord les données de base.")
                else:
                    st.success(f"{inserted_rows} mesures ont été insérées.")
            except Exception as exc:  # noqa: BLE001
                st.error(f"Génération impossible: {exc}")

    with tab_nl:
        st.subheader("Tester le compilateur français → SQL")
        prompt = st.text_input(
            "Prompt",
            value="Affiche les 5 zones les plus polluées",
        )
        if prompt.strip():
            try:
                sql_query = compiler.compile(prompt)
                st.code(sql_query, language="sql")
                if st.button("Exécuter la requête compilée", use_container_width=True):
                    result = run_select(settings, sql_query.rstrip(";"))
                    st.dataframe(result, use_container_width=True, height=420)
            except Exception as exc:  # noqa: BLE001
                st.error(f"Compilation impossible: {exc}")


if __name__ == "__main__":
    main()
