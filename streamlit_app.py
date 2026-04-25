from __future__ import annotations

from contextlib import closing
from dataclasses import dataclass
from datetime import datetime, timedelta

import mysql.connector
import pandas as pd
import streamlit as st
from mysql.connector import Error

from ai_reports import AIProviderConfig, build_report_context, generate_ai_report
from automata import AUTOMATA, available_events, detect_sensor_value_alerts, validate_sequence
from seed_data import (
    REFERENCE_CITIZENS,
    REFERENCE_MEASURES,
    REFERENCE_VEHICLES,
    attach_measure_ids_to_capteurs,
    generate_capteur_rows,
    generate_citizen_rows,
    generate_intervention_rows,
    generate_measure_rows,
    generate_measure_and_capteur_rows,
    generate_standalone_measure_rows,
    generate_vehicle_rows,
)
from sql_compiler import FrenchSQLCompiler


APP_TITLE = "CompCodex MySQL Console"
DATABASE_NAME = "compcodex_db"
CAPTEUR_ETATS = ["inactif", "actif", "signale", "en maintenance", "hors service"]
VEHICULE_ETATS = ["stationne", "en route", "en panne", "arrive"]
TABLES = ["citoyens", "vehicule", "capteur", "mesure", "intervention"]
AUTOMATA_DEFAULT_EVENTS = {
    "capteur": "installation, detection anomalie, reparation",
    "intervention": "assigner tech1, valider tech2, valider ia, cloturer",
    "vehicule": "demarrer, panne, reparer, arrive",
}


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
    rows: list[tuple[float | None, str, str, datetime | str]],
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


def insert_citizen_rows(settings: ConnectionSettings, count: int) -> int:
    return run_statement(
        settings,
        "INSERT INTO citoyens (nom, prenom, adresse, telephone) VALUES (%s, %s, %s, %s)",
        generate_citizen_rows(count),
        many=True,
    )


def insert_vehicle_rows(settings: ConnectionSettings, count: int) -> int:
    return run_statement(
        settings,
        "INSERT INTO vehicule (immatriculation, modele, etat_vehicule, date_mise_service) VALUES (%s, %s, %s, %s)",
        generate_vehicle_rows(count),
        many=True,
    )


def insert_capteur_rows(settings: ConnectionSettings, count: int) -> int:
    measure_rows, capteur_rows_without_measure_id = generate_measure_and_capteur_rows(count)
    measure_ids = insert_measure_rows(settings, measure_rows)
    capteur_rows = attach_measure_ids_to_capteurs(
        capteur_rows_without_measure_id,
        measure_ids,
    )
    return run_statement(
        settings,
        "INSERT INTO capteur (type_capteur, localisation, date_installation, etat_capteur, id_mesure) VALUES (%s, %s, %s, %s, %s)",
        capteur_rows,
        many=True,
    )


def ensure_capteurs_for_interventions(
    settings: ConnectionSettings,
    required_count: int,
) -> list[int]:
    capteur_ids = fetch_ids(settings, "capteur", "id_capteur")
    if capteur_ids:
        return capteur_ids

    measure_ids = insert_measure_rows(settings, generate_standalone_measure_rows(required_count))
    capteur_rows = generate_capteur_rows(measure_ids)
    run_statement(
        settings,
        "INSERT INTO capteur (type_capteur, localisation, date_installation, etat_capteur, id_mesure) VALUES (%s, %s, %s, %s, %s)",
        capteur_rows,
        many=True,
    )
    return fetch_ids(settings, "capteur", "id_capteur")


def insert_intervention_rows(settings: ConnectionSettings, count: int) -> int:
    capteur_ids = ensure_capteurs_for_interventions(settings, count)
    return run_statement(
        settings,
        "INSERT INTO intervention (date_demande, date_debut, date_fin, statut_intervention, id_capteur) VALUES (%s, %s, %s, %s, %s)",
        generate_intervention_rows(capteur_ids, count),
        many=True,
    )


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


def generate_table_objects(
    settings: ConnectionSettings,
    target_table: str,
    count: int,
) -> dict[str, int]:
    if count <= 0:
        return {}

    if target_table == "citoyens":
        return {"citoyens": insert_citizen_rows(settings, count)}
    if target_table == "vehicule":
        return {"vehicule": insert_vehicle_rows(settings, count)}
    if target_table == "mesure":
        return {"mesure": len(insert_measure_rows(settings, generate_standalone_measure_rows(count)))}
    if target_table == "capteur":
        inserted_capteurs = insert_capteur_rows(settings, count)
        return {"mesure": count, "capteur": inserted_capteurs}
    if target_table == "intervention":
        return {"intervention": insert_intervention_rows(settings, count)}
    if target_table == "all":
        inserted = {
            "citoyens": insert_citizen_rows(settings, count),
            "vehicule": insert_vehicle_rows(settings, count),
        }
        measure_rows, capteur_rows_without_measure_id = generate_measure_and_capteur_rows(count)
        measure_ids = insert_measure_rows(settings, measure_rows)
        capteur_rows = attach_measure_ids_to_capteurs(
            capteur_rows_without_measure_id,
            measure_ids,
        )
        inserted["mesure"] = len(measure_ids)
        inserted["capteur"] = run_statement(
            settings,
            "INSERT INTO capteur (type_capteur, localisation, date_installation, etat_capteur, id_mesure) VALUES (%s, %s, %s, %s, %s)",
            capteur_rows,
            many=True,
        )
        inserted["intervention"] = insert_intervention_rows(settings, count)
        return inserted

    raise ValueError(f"Table inconnue: {target_table}")


def seed_reference_data(settings: ConnectionSettings) -> dict[str, int]:
    inserted: dict[str, int] = {}

    if table_count(settings, "citoyens") == 0:
        inserted["citoyens"] = run_statement(
            settings,
            "INSERT INTO citoyens (nom, prenom, adresse, telephone) VALUES (%s, %s, %s, %s)",
            REFERENCE_CITIZENS,
            many=True,
        )
    else:
        inserted["citoyens"] = 0

    if table_count(settings, "vehicule") == 0:
        inserted["vehicule"] = run_statement(
            settings,
            "INSERT INTO vehicule (immatriculation, modele, etat_vehicule, date_mise_service) VALUES (%s, %s, %s, %s)",
            REFERENCE_VEHICLES,
            many=True,
        )
    else:
        inserted["vehicule"] = 0

    existing_measure_ids = fetch_ids(settings, "mesure", "id_mesure")
    if len(existing_measure_ids) < 6:
        missing_count = 6 - len(existing_measure_ids)
        inserted_measure_ids = insert_measure_rows(settings, REFERENCE_MEASURES[:missing_count])
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
            ("pollution", "Nabeul Plage", "2024-04-26", "inactif", measure_ids[5]),
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


def load_sensor_action_records(settings: ConnectionSettings) -> list[dict]:
    query = """
        SELECT
            c.id_capteur,
            c.etat_capteur,
            c.id_mesure,
            m.valeur,
            m.horodatage
        FROM capteur c
        JOIN mesure m ON c.id_mesure = m.id_mesure
        ORDER BY c.id_capteur
    """
    return run_select(settings, query).to_dict("records")


def load_ai_report_frames(settings: ConnectionSettings) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    sensors_query = """
        SELECT
            c.id_capteur,
            c.type_capteur,
            c.localisation,
            c.etat_capteur,
            c.date_installation,
            m.valeur,
            m.unite,
            m.type_mesure,
            m.horodatage
        FROM capteur c
        JOIN mesure m ON c.id_mesure = m.id_mesure
        ORDER BY c.localisation, c.id_capteur
    """
    interventions_query = """
        SELECT
            i.id_intervention,
            i.statut_intervention,
            i.date_demande,
            i.date_debut,
            i.date_fin,
            i.id_capteur,
            c.localisation
        FROM intervention i
        JOIN capteur c ON c.id_capteur = i.id_capteur
        ORDER BY i.date_demande DESC
        LIMIT 50
    """
    pollution_query = """
        SELECT
            c.localisation,
            ROUND(AVG(m.valeur), 2) AS moyenne_pollution,
            COUNT(*) AS nombre_mesures
        FROM capteur c
        JOIN mesure m ON c.id_mesure = m.id_mesure
        WHERE m.type_mesure = 'pollution' AND m.valeur IS NOT NULL
        GROUP BY c.localisation
        ORDER BY moyenne_pollution DESC
        LIMIT 10
    """
    return (
        run_select(settings, sensors_query),
        run_select(settings, interventions_query),
        run_select(settings, pollution_query),
    )


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


def parse_event_sequence(raw_events: str) -> list[str]:
    return [
        event.strip()
        for line in raw_events.splitlines()
        for event in line.split(",")
        if event.strip()
    ]


def render_automata_tab(
    settings: ConnectionSettings,
    db_error: Error | None,
) -> None:
    st.subheader("Automates")

    left, right = st.columns([1, 2])
    with left:
        entity_type = st.selectbox(
            "Entité",
            options=list(AUTOMATA.keys()),
            format_func=lambda value: value.capitalize(),
        )
        automaton = AUTOMATA[entity_type]
        initial_state = st.selectbox(
            "État initial",
            options=sorted(automaton.states),
            index=sorted(automaton.states).index(automaton.initial_state),
        )
        st.caption("Événements possibles depuis cet état")
        st.write(", ".join(available_events(entity_type, initial_state)) or "Aucun")

    with right:
        raw_events = st.text_area(
            "Séquence d'événements",
            value=AUTOMATA_DEFAULT_EVENTS[entity_type],
            height=120,
            help="Sépare les événements par des virgules ou par ligne.",
        )
        events = parse_event_sequence(raw_events)
        result = validate_sequence(entity_type, events, initial_state)

        status = "Valide" if result.valid else "Invalide"
        st.metric("Statut", status)
        st.metric("État courant", result.current_state)

        if result.errors:
            for error in result.errors:
                st.error(error)

    st.divider()
    st.subheader("Actions automatiques")
    st.caption("Seuil de simulation: 1 minute sans valeur.")

    try:
        if db_error is None:
            sensor_records = load_sensor_action_records(settings)
        else:
            sensor_records = [
                {
                    "id_capteur": "simulation-1",
                    "etat_capteur": "hors service",
                    "id_mesure": "simulation-1",
                    "valeur": None,
                    "horodatage": datetime.now() - timedelta(minutes=2),
                }
            ]

        actions = detect_sensor_value_alerts(sensor_records)
        if actions:
            st.dataframe(pd.DataFrame(actions), width="stretch", height=180)
        else:
            st.info("Aucune action automatique déclenchée.")
    except Exception as exc:  # noqa: BLE001
        st.error(f"Évaluation automatique impossible: {exc}")


def render_ai_reports_tab(
    settings: ConnectionSettings,
    db_error: Error | None,
) -> None:
    st.subheader("Rapports générés par IA")

    if db_error is not None:
        st.error(f"Connexion MySQL impossible: {db_error}")
        st.info("La génération de rapport nécessite les données de la base.")
        return

    with st.expander("Configuration du modèle", expanded=False):
        st.caption(
            "Compatible avec les APIs de type OpenAI Chat Completions. "
            "Sans configuration complète, l'application utilise le générateur local."
        )
        col_model, col_url = st.columns([1, 2])
        with col_model:
            model = st.text_input(
                "Modèle",
                value="",
                placeholder="grok-..., kimi-k2.6...",
            )
        with col_url:
            base_url = st.text_input(
                "Base URL",
                value="",
                placeholder="https://.../v1",
            )
        api_key = st.text_input("API key", type="password", value="")

    if st.button("Générer le rapport IA", type="primary", width="stretch"):
        try:
            sensors, interventions, polluted_zones = load_ai_report_frames(settings)
            context = build_report_context(sensors, interventions, polluted_zones)
            config = AIProviderConfig(
                api_key=api_key,
                base_url=base_url,
                model=model or "local-deterministic",
            )
            result = generate_ai_report(context, config)
            st.session_state["ai_report_result"] = result
            st.session_state["ai_report_context"] = context
        except Exception as exc:  # noqa: BLE001
            st.error(f"Rapport impossible: {exc}")

    result = st.session_state.get("ai_report_result")
    context = st.session_state.get("ai_report_context")
    if not result or not context:
        st.info("Clique sur le bouton pour produire un rapport à partir des données courantes.")
        return

    source_label = result["source"]
    st.caption(f"Source: {source_label} | temps: {result['elapsed_ms']} ms")
    if result["error"]:
        st.warning(f"Le fournisseur IA a échoué; rapport local utilisé. Détail: {result['error']}")

    st.text_area("Rapport", value=result["report"], height=300)

    st.subheader("Actions suggérées")
    st.dataframe(pd.DataFrame(result["actions"]), width="stretch", height=220)

    st.subheader("Indicateurs utilisés")
    st.json(context["counts"])


def main() -> None:
    st.set_page_config(page_title=APP_TITLE, layout="wide")
    st.title(APP_TITLE)
    st.caption("Visualiser les tables MySQL, générer des données réalistes et tester le compilateur NL → SQL.")

    settings = build_sidebar()
    compiler = FrenchSQLCompiler()

    db_error: Error | None = None
    try:
        counts = {table: table_count(settings, table) for table in TABLES}
    except Error as exc:
        counts = {}
        db_error = exc

    if counts:
        metrics = st.columns(len(TABLES))
        for index, table in enumerate(TABLES):
            metrics[index].metric(table, counts[table])

    tab_data, tab_seed, tab_nl, tab_automata, tab_reports = st.tabs(
        ["Tables", "Génération", "NL → SQL", "Automates", "Rapports IA"]
    )

    with tab_data:
        if db_error is not None:
            st.error(f"Connexion MySQL impossible: {db_error}")
            st.info("Assure-toi d'avoir exécuté `mysql -u root -p < schema_mysql.sql` avant d'ouvrir l'application.")
        else:
            left, right = st.columns([1, 2])
            with left:
                selected_table = st.selectbox("Table", TABLES)
                preview_limit = st.slider("Nombre de lignes", min_value=5, max_value=200, value=25, step=5)
            with right:
                preview = load_table_preview(settings, selected_table, preview_limit)
                st.dataframe(preview, width="stretch", height=520)

            if counts["mesure"] > 0:
                st.subheader("Aperçu analytique des mesures")
                st.dataframe(load_stats(settings), width="stretch", height=320)

    with tab_seed:
        if db_error is not None:
            st.error(f"Connexion MySQL impossible: {db_error}")
            st.info("La génération de données nécessite une connexion MySQL active.")
        else:
            st.subheader("Jeu de données de démonstration")
            st.write("1. Insère citoyens, véhicules, capteurs et interventions si les tables sont vides.")
            if st.button("Insérer les données de base", width="stretch"):
                try:
                    inserted = seed_reference_data(settings)
                    st.success(
                        "Insertion terminée: "
                        + ", ".join(f"{table}={count}" for table, count in inserted.items())
                    )
                except Exception as exc:  # noqa: BLE001
                    st.error(f"Insertion impossible: {exc}")

            st.divider()
            st.subheader("Génération en masse")
            table_options = {
                "Toutes les tables": "all",
                "Citoyens": "citoyens",
                "Véhicules": "vehicule",
                "Mesures": "mesure",
                "Capteurs": "capteur",
                "Interventions": "intervention",
            }
            bulk_left, bulk_right = st.columns([2, 1])
            with bulk_left:
                selected_generation_label = st.selectbox(
                    "Table à générer",
                    options=list(table_options.keys()),
                )
            with bulk_right:
                object_count = st.number_input(
                    "Nombre d'objets",
                    min_value=1,
                    max_value=10_000,
                    value=100,
                    step=10,
                )

            if st.button("Générer les objets", type="primary", width="stretch"):
                try:
                    inserted = generate_table_objects(
                        settings,
                        table_options[selected_generation_label],
                        int(object_count),
                    )
                    st.success(
                        "Génération terminée: "
                        + ", ".join(f"{table}={count}" for table, count in inserted.items())
                    )
                except Exception as exc:  # noqa: BLE001
                    st.error(f"Génération impossible: {exc}")

            st.divider()
            st.subheader("Génération réaliste de mesures")
            per_sensor = st.slider("Mesures par capteur", min_value=12, max_value=720, value=48, step=12)
            step_minutes = st.select_slider("Intervalle temporel", options=[5, 10, 15, 30, 60], value=30)
            st.caption("Les capteurs `hors service` ne génèrent pas de mesures. Le schéma relie chaque capteur à une mesure courante via `id_mesure`.")

            if st.button("Générer des mesures", type="primary", width="stretch"):
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
                if st.button("Exécuter la requête compilée", width="stretch"):
                    if db_error is not None:
                        st.error(f"Connexion MySQL impossible: {db_error}")
                    else:
                        result = run_select(settings, sql_query.rstrip(";"))
                        st.dataframe(result, width="stretch", height=420)
            except Exception as exc:  # noqa: BLE001
                st.error(f"Compilation impossible: {exc}")

    with tab_automata:
        render_automata_tab(settings, db_error)

    with tab_reports:
        render_ai_reports_tab(settings, db_error)


if __name__ == "__main__":
    main()
