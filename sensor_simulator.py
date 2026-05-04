from __future__ import annotations

import argparse
import time
from contextlib import closing
from dataclasses import dataclass

import mysql.connector

from seed_data import generate_live_measure_row


DEFAULT_DATABASE_NAME = "compcodex_db"
DEFAULT_INTERVAL_MINUTES = 30


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


def fetch_sensor_records(
    settings: ConnectionSettings,
) -> list[tuple[int, str, str, int, float | None]]:
    with closing(get_connection(settings)) as connection:
        cursor = connection.cursor()
        cursor.execute(
            """
            SELECT c.id_capteur, c.type_capteur, c.etat_capteur, c.id_mesure, m.valeur
            FROM capteur c
            JOIN mesure m ON m.id_mesure = c.id_mesure
            ORDER BY c.id_capteur
            """
        )
        return cursor.fetchall()


def update_measure_rows(
    settings: ConnectionSettings,
    rows: list[tuple[float | None, str, str, object, int]],
) -> int:
    with closing(get_connection(settings)) as connection:
        cursor = connection.cursor()
        cursor.executemany(
            """
            UPDATE mesure
            SET valeur = %s, unite = %s, type_mesure = %s, horodatage = %s
            WHERE id_mesure = %s
            """,
            rows,
        )
        connection.commit()
        return cursor.rowcount


def simulate_sensor_cycle(settings: ConnectionSettings) -> tuple[int, int]:
    sensor_records = fetch_sensor_records(settings)
    measure_updates: list[tuple[float | None, str, str, object, int]] = []

    for _sensor_id, sensor_type, sensor_state, measure_id, current_value in sensor_records:
        if sensor_state == "hors service":
            continue
        next_value, unit, measure_type, timestamp = generate_live_measure_row(
            sensor_type=sensor_type,
            sensor_state=sensor_state,
            current_value=current_value,
        )
        measure_updates.append((next_value, unit, measure_type, timestamp, measure_id))

    if not measure_updates:
        return (0, 0)

    updated_measures = update_measure_rows(settings, measure_updates)
    return (updated_measures, len(measure_updates))


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Simule la mise a jour periodique des capteurs en mettant a jour "
            "les lignes mesure deja liees par capteur.id_mesure."
        )
    )
    parser.add_argument("--host", default="localhost")
    parser.add_argument("--port", type=int, default=3306)
    parser.add_argument("--user", default="root")
    parser.add_argument("--password", default="")
    parser.add_argument("--database", default=DEFAULT_DATABASE_NAME)
    parser.add_argument(
        "--interval-minutes",
        type=float,
        default=DEFAULT_INTERVAL_MINUTES,
        help="Intervalle entre deux cycles. Production: 30. Test: 1.",
    )
    parser.add_argument(
        "--iterations",
        type=int,
        default=0,
        help="Nombre de cycles a executer. 0 signifie execution continue.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    settings = ConnectionSettings(
        host=args.host,
        port=args.port,
        user=args.user,
        password=args.password,
        database=args.database,
    )

    interval_seconds = max(args.interval_minutes, 0.1) * 60
    cycle = 0

    while True:
        cycle += 1
        updated_measures, processed_sensors = simulate_sensor_cycle(settings)
        print(
            f"[cycle {cycle}] updated_mesures={updated_measures} processed_sensors={processed_sensors} "
            f"interval_minutes={args.interval_minutes}",
            flush=True,
        )

        if args.iterations and cycle >= args.iterations:
            break

        time.sleep(interval_seconds)


if __name__ == "__main__":
    main()
