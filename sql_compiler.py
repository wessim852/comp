import re
import sys
import unicodedata
from dataclasses import dataclass


def _strip_accents(text: str) -> str:
    normalized = unicodedata.normalize("NFKD", text)
    return "".join(char for char in normalized if not unicodedata.combining(char))


def _normalize_text(text: str) -> str:
    text = _strip_accents(text).lower()
    text = text.replace("’", "'")
    text = re.sub(r"\s+", " ", text).strip()
    return text


@dataclass(frozen=True)
class Schema:
    tables: dict[str, list[str]]
    aliases: dict[str, str]


SCHEMA = Schema(
    tables={
        "citoyens": [
            "id_citoyen",
            "nom",
            "prenom",
            "adresse",
            "telephone",
        ],
        "vehicule": [
            "id_vehicule",
            "immatriculation",
            "modele",
            "etat_vehicule",
            "date_mise_service",
        ],
        "capteur": [
            "id_capteur",
            "type_capteur",
            "localisation",
            "date_installation",
            "etat_capteur",
            "id_mesure",
        ],
        "mesure": [
            "id_mesure",
            "valeur",
            "unite",
            "type_mesure",
            "horodatage",
        ],
        "intervention": [
            "id_intervention",
            "date_demande",
            "date_debut",
            "date_fin",
            "statut_intervention",
            "id_capteur",
        ],
    },
    aliases={
        "citoyen": "citoyens",
        "citoyens": "citoyens",
        "vehicule": "vehicule",
        "vehicules": "vehicule",
        "capteur": "capteur",
        "capteurs": "capteur",
        "mesure": "mesure",
        "mesures": "mesure",
        "intervention": "intervention",
        "interventions": "intervention",
        "etat vehicule": "etat_vehicule",
        "date mise service": "date_mise_service",
    },
)


class FrenchSQLCompiler:
    def __init__(self, schema: Schema = SCHEMA):
        self.schema = schema
        self.column_aliases = self._build_column_aliases()

    def _build_column_aliases(self) -> dict[str, str]:
        aliases: dict[str, str] = {}
        for columns in self.schema.tables.values():
            for column in columns:
                normalized = _normalize_text(column.replace("_", " "))
                aliases[normalized] = column
                aliases[_normalize_text(column)] = column
        for alias, column in self.schema.aliases.items():
            if column in aliases.values():
                aliases[_normalize_text(alias)] = column
        return aliases

    def _column_aliases_for_table(self, table: str) -> list[tuple[str, str]]:
        variants: set[tuple[str, str]] = set()
        for column in self.schema.tables[table]:
            variants.add((_normalize_text(column), column))
            variants.add((_normalize_text(column.replace("_", " ")), column))
        for alias, column in self.column_aliases.items():
            if column in self.schema.tables[table]:
                variants.add((alias, column))
        return sorted(variants, key=lambda item: len(item[0]), reverse=True)

    def compile(self, prompt: str) -> str:
        normalized = _normalize_text(prompt)

        if "zone" in normalized and "pollu" in normalized:
            return self._compile_top_polluted_zones(normalized)

        table = self._detect_table(normalized)
        if not table:
            raise ValueError(f"Impossible de determiner la table cible pour: {prompt}")

        if "moyenne" in normalized and "groupe par" in normalized:
            return self._compile_grouped_average(normalized, table)

        if normalized.startswith("combien") or "combien de" in normalized:
            return self._compile_count(normalized, table)

        return self._compile_select(normalized, table)

    def _detect_table(self, normalized: str) -> str | None:
        for alias, table in self.schema.aliases.items():
            if _normalize_text(alias) in normalized and table in self.schema.tables:
                return table
        return None

    def _extract_limit(self, normalized: str) -> int | None:
        match = re.search(r"\b(\d+)\b", normalized)
        if match:
            return int(match.group(1))
        return None

    def _compile_top_polluted_zones(self, normalized: str) -> str:
        limit = self._extract_limit(normalized) or 5
        return (
            "SELECT c.localisation, AVG(m.valeur) AS moyenne_pollution "
            "FROM mesure m "
            "JOIN capteur c ON c.id_mesure = m.id_mesure "
            "WHERE m.type_mesure = 'pollution' "
            "GROUP BY c.localisation "
            "ORDER BY moyenne_pollution DESC "
            f"LIMIT {limit};"
        )

    def _compile_grouped_average(self, normalized: str, table: str) -> str:
        metric = self._resolve_column("valeur", table)
        group_match = re.search(r"groupe par ([a-z0-9_ ]+)", normalized)
        if not group_match:
            raise ValueError("La colonne de groupement est manquante.")
        group_column = self._resolve_column(group_match.group(1).strip(), table)
        return (
            f"SELECT {group_column}, AVG({metric}) AS moyenne_{metric} "
            f"FROM {table} "
            f"GROUP BY {group_column};"
        )

    def _compile_count(self, normalized: str, table: str) -> str:
        conditions = self._extract_conditions(normalized, table)
        alias = f"nombre_{table}"
        query = f"SELECT COUNT(*) AS {alias} FROM {table}"
        if conditions:
            query += f" WHERE {' AND '.join(conditions)}"
        return query + ";"

    def _compile_select(self, normalized: str, table: str) -> str:
        conditions = self._extract_conditions(normalized, table)
        order_by = self._extract_order_by(normalized, table)
        limit = self._extract_limit_from_listing(normalized, table)

        query = f"SELECT * FROM {table}"
        if conditions:
            query += f" WHERE {' AND '.join(conditions)}"
        if order_by:
            query += f" ORDER BY {order_by}"
        if limit is not None:
            query += f" LIMIT {limit}"
        return query + ";"

    def _extract_limit_from_listing(self, normalized: str, table: str) -> int | None:
        if not any(keyword in normalized for keyword in ("affiche", "montre", "liste", "donne")):
            return None

        head = re.split(r"\b(ou|avec|quand|dont)\b", normalized, maxsplit=1)[0]
        if not any(alias in head for alias, candidate in self.schema.aliases.items() if candidate == table):
            return None

        match = re.search(r"\b(\d+)\b", head)
        if match:
            return int(match.group(1))
        return None

    def _extract_order_by(self, normalized: str, table: str) -> str | None:
        match = re.search(
            r"tri(?:e|es|ez|er)s? par ([a-z0-9_ ]+?) (decroissant|croissant)",
            normalized,
        )
        if not match:
            return None
        column = self._resolve_column(match.group(1).strip(), table)
        direction = "DESC" if match.group(2) == "decroissant" else "ASC"
        return f"{column} {direction}"

    def _extract_conditions(self, normalized: str, table: str) -> list[str]:
        ranked_conditions: list[tuple[int, str]] = []
        for alias, column in self._column_aliases_for_table(table):
            between_pattern = re.finditer(
                rf"(?:^|[^a-z0-9_])(?:le |la |les |l')?{re.escape(alias)}\s+entre\s+"
                r"([0-9]+(?:\.[0-9]+)?)\s+et\s+([0-9]+(?:\.[0-9]+)?)",
                normalized,
            )
            for match in between_pattern:
                clause = f"{column} BETWEEN {match.group(1)} AND {match.group(2)}"
                ranked_conditions.append((match.start(), clause))

            explicit_pattern = re.finditer(
                rf"(?:^|[^a-z0-9_]){re.escape(alias)}\s*(=|>=|<=|>|<)\s*"
                r"('(?:[^']*)'|[0-9]+(?:\.[0-9]+)?)",
                normalized,
            )
            for match in explicit_pattern:
                clause = f"{column} {match.group(1)} {match.group(2)}"
                ranked_conditions.append((match.start(), clause))

        conditions: list[str] = []
        for _, clause in sorted(ranked_conditions, key=lambda item: item[0]):
            if clause not in conditions:
                conditions.append(clause)

        inferred_equals = self._extract_implicit_text_equals(normalized, table, conditions)
        for clause in inferred_equals:
            if clause not in conditions:
                conditions.append(clause)

        if "hors service" in normalized and table == "capteur":
            clause = "etat_capteur = 'hors service'"
            if clause not in conditions:
                conditions.append(clause)

        if "en cours" in normalized and table == "intervention":
            clause = "statut_intervention = 'en_cours'"
            if clause not in conditions:
                conditions.append(clause)

        if "terminee" in normalized or "terminees" in normalized:
            if table == "intervention":
                clause = "statut_intervention = 'terminee'"
                if clause not in conditions:
                    conditions.append(clause)

        if "adresse =" not in normalized:
            address_match = re.search(r"adresse de '?([^']+)'?$", normalized)
            if address_match and table == "citoyens":
                conditions.append(f"adresse = '{address_match.group(1)}'")

        return conditions

    def _extract_implicit_text_equals(
        self,
        normalized: str,
        table: str,
        existing_conditions: list[str],
    ) -> list[str]:
        clauses: list[tuple[int, str]] = []
        textual_columns = [
            column
            for column in self.schema.tables[table]
            if not column.startswith("id_")
            and not column.startswith("date_")
            and column not in {"telephone", "valeur"}
        ]

        for alias, column in self._column_aliases_for_table(table):
            if column not in textual_columns:
                continue
            if any(condition.startswith(f"{column} ") for condition in existing_conditions):
                continue

            pattern = re.finditer(
                rf"(?:^|[^a-z0-9_])(?:qui ont |qui a |avec |ayant |dont |ou )?"
                rf"(?:le |la |les |l')?{re.escape(alias)}\s+"
                r"([a-z0-9_-]+(?: [a-z0-9_-]+){0,2})"
                r"(?=$| [?]| et | ou | tri| group| ordre| limit)",
                normalized,
            )
            for match in pattern:
                value = match.group(1).strip()
                if value in {"croissant", "decroissant"}:
                    continue
                clauses.append((match.start(), f"{column} = '{value}'"))

        deduped: list[str] = []
        for _, clause in sorted(clauses, key=lambda item: item[0]):
            if clause not in deduped:
                deduped.append(clause)
        return deduped

    def _resolve_column(self, raw_column: str, table: str) -> str:
        normalized = _normalize_text(raw_column.replace("_", " "))
        if normalized in self.column_aliases:
            column = self.column_aliases[normalized]
            if column in self.schema.tables[table]:
                return column

        normalized = _normalize_text(raw_column)
        if normalized in self.column_aliases:
            column = self.column_aliases[normalized]
            if column in self.schema.tables[table]:
                return column

        raise ValueError(f"Colonne inconnue pour {table}: {raw_column}")


if __name__ == "__main__":
    compiler = FrenchSQLCompiler()
    if len(sys.argv) > 1:
        prompt = " ".join(sys.argv[1:])
        print(compiler.compile(prompt))
    else:
        examples = [
            "Affiche les 5 zones les plus polluées",
            "Combien de capteurs sont hors service ?",
            "Donne-moi les interventions en cours où statut_intervention = 'en_cours'",
            "Montre les mesures où valeur > 50 et type_mesure = 'pollution'",
            "Liste les citoyens où adresse = 'Sousse'",
            "Moyenne de valeur des mesures groupé par type_mesure",
            "Affiche les capteurs triés par date_installation décroissant",
            "Affiche les 3 véhicules",
            "Quels citoyens ont le téléphone entre 20000000 et 29999999",
            "Combien d'interventions sont terminées ?",
        ]
        for prompt in examples:
            print(prompt)
            print(compiler.compile(prompt))
