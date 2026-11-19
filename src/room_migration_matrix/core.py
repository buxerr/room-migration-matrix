"""Validate Room schema and migration coverage, then render test cases."""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass
import json
from pathlib import Path
import re
from typing import Iterable


class MatrixError(ValueError):
    """Raised when inputs cannot form a trustworthy migration matrix."""


@dataclass(frozen=True, order=True)
class Migration:
    start: int
    end: int
    symbol: str


@dataclass(frozen=True)
class Scenario:
    start: int
    end: int
    migrations: tuple[Migration, ...]


_SYMBOL = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*(?:\.[A-Za-z_][A-Za-z0-9_]*)*$")
_IDENTIFIER = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


def load_schemas(directory: Path) -> tuple[int, ...]:
    """Read Room-exported JSON schemas recursively and return their versions."""
    if not directory.is_dir():
        raise MatrixError(f"schema directory does not exist: {directory}")
    versions: dict[int, Path] = {}
    files = sorted(directory.rglob("*.json"))
    if not files:
        raise MatrixError("schema directory contains no JSON files")
    for path in files:
        try:
            value = json.loads(path.read_text(encoding="utf-8"))
            database = value["database"]
            version = database["version"]
        except (OSError, json.JSONDecodeError, KeyError, TypeError) as error:
            raise MatrixError(f"invalid Room schema file {path}: expected database.version") from error
        if isinstance(version, bool) or not isinstance(version, int) or version < 1:
            raise MatrixError(f"invalid Room schema version in {path}: expected positive integer")
        if version in versions:
            raise MatrixError(f"duplicate Room schema version {version}: {versions[version]} and {path}")
        versions[version] = path
    if len(versions) < 2:
        raise MatrixError("at least two exported Room schema versions are required")
    return tuple(sorted(versions))


def load_migrations(path: Path, versions: Iterable[int]) -> tuple[Migration, ...]:
    """Read explicit migration symbols from a JSON manifest."""
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise MatrixError(f"cannot read migration manifest {path}: {error}") from error
    if not isinstance(value, dict) or not isinstance(value.get("migrations"), list):
        raise MatrixError("migration manifest must contain a migrations array")
    known_versions = set(versions)
    edges: list[Migration] = []
    seen_pairs: set[tuple[int, int]] = set()
    for item in value["migrations"]:
        if not isinstance(item, dict):
            raise MatrixError("each migration entry must be an object")
        start, end, symbol = item.get("from"), item.get("to"), item.get("symbol")
        if (isinstance(start, bool) or not isinstance(start, int) or isinstance(end, bool)
                or not isinstance(end, int) or start < 1 or end <= start):
            raise MatrixError("migration from/to must be positive, increasing integer versions")
        if not isinstance(symbol, str) or not _SYMBOL.fullmatch(symbol):
            raise MatrixError(f"invalid Kotlin migration expression for {start}->{end}")
        if start not in known_versions or end not in known_versions:
            raise MatrixError(f"migration {start}->{end} has no matching exported schema version")
        pair = (start, end)
        if pair in seen_pairs:
            raise MatrixError(f"duplicate migration edge {start}->{end}")
        seen_pairs.add(pair)
        edges.append(Migration(start, end, symbol))
    return tuple(sorted(edges))


def build_matrix(versions: Iterable[int], migrations: Iterable[Migration]) -> tuple[Scenario, ...]:
    """Choose a deterministic shortest migration path for every forward pair."""
    ordered_versions = tuple(sorted(set(versions)))
    edges = tuple(migrations)
    if len(ordered_versions) < 2:
        raise MatrixError("at least two schema versions are required")
    if any(isinstance(v, bool) or not isinstance(v, int) or v < 1 for v in ordered_versions):
        raise MatrixError("schema versions must be positive integers")
    graph: dict[int, list[Migration]] = {version: [] for version in ordered_versions}
    seen: set[tuple[int, int]] = set()
    for edge in edges:
        if edge.start not in graph or edge.end not in graph or edge.end <= edge.start:
            raise MatrixError(f"invalid migration edge {edge.start}->{edge.end}")
        if not _SYMBOL.fullmatch(edge.symbol):
            raise MatrixError(f"invalid Kotlin migration expression for {edge.start}->{edge.end}")
        if (edge.start, edge.end) in seen:
            raise MatrixError(f"duplicate migration edge {edge.start}->{edge.end}")
        seen.add((edge.start, edge.end))
        graph[edge.start].append(edge)
    for outgoing in graph.values():
        outgoing.sort(key=lambda edge: (edge.end, edge.symbol))

    scenarios: list[Scenario] = []
    for source_index, start in enumerate(ordered_versions[:-1]):
        for end in ordered_versions[source_index + 1:]:
            queue = deque([(start, ())])
            visited = {start}
            path: tuple[Migration, ...] | None = None
            while queue:
                current, path_so_far = queue.popleft()
                if current == end:
                    path = path_so_far
                    break
                for edge in graph[current]:
                    if edge.end <= end and edge.end not in visited:
                        visited.add(edge.end)
                        queue.append((edge.end, path_so_far + (edge,)))
            if path is None:
                raise MatrixError(f"no migration path from schema {start} to schema {end}")
            scenarios.append(Scenario(start, end, path))
    return tuple(scenarios)


def render_kotlin(
    scenarios: Iterable[Scenario],
    package: str,
    helper: str = "migrationTestHelper",
    database_name: str = "MigrationMatrix",
    imports: Iterable[str] = (),
) -> str:
    """Render a compilable Kotlin helper that runs the generated test matrix."""
    if package and not all(_IDENTIFIER.fullmatch(part) for part in package.split(".")):
        raise MatrixError("invalid Kotlin package name")
    if not _IDENTIFIER.fullmatch(helper):
        raise MatrixError("helper must be a Kotlin identifier")
    if not _IDENTIFIER.fullmatch(database_name):
        raise MatrixError("database name must be a Kotlin identifier")
    extra_imports = tuple(sorted(set(imports)))
    if any(not _SYMBOL.fullmatch(item) for item in extra_imports):
        raise MatrixError("imports must be fully qualified Kotlin names")
    cases = tuple(scenarios)
    lines: list[str] = []
    if package:
        lines.extend((f"package {package}", ""))
    lines.append("import androidx.room.testing.MigrationTestHelper")
    lines.extend(f"import {item}" for item in extra_imports)
    lines.extend(("", "// Generated by room-migration-matrix. Call this from an Android instrumented test.",
                  f"fun runGeneratedMigrationMatrix({helper}: MigrationTestHelper) {{"))
    for case in cases:
        migration_list = ", ".join(edge.symbol for edge in case.migrations)
        db_name = f'"{database_name}_{case.start}_{case.end}"'
        lines.extend((
            f"    {helper}.createDatabase({db_name}, {case.start}).close()",
            f"    {helper}.runMigrationsAndValidate({db_name}, {case.end}, true, {migration_list}).close()",
        ))
    lines.extend(("}", ""))
    return "\n".join(lines)
