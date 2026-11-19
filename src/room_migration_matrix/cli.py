"""Command line entry point."""

import argparse
import json
from pathlib import Path
import sys

from .core import MatrixError, build_matrix, load_migrations, load_schemas, render_kotlin


def main() -> int:
    parser = argparse.ArgumentParser(description="Generate Room MigrationTestHelper tests for every exported forward version pair.")
    parser.add_argument("--schemas", type=Path, required=True, help="Room schema export directory")
    parser.add_argument("--migrations", type=Path, required=True, help="JSON file mapping version edges to Kotlin migration expressions")
    parser.add_argument("--package", default="", help="Kotlin package name for generated source")
    parser.add_argument("--helper", default="migrationTestHelper", help="MigrationTestHelper field name in your test class")
    parser.add_argument("--migration-import", action="append", default=[], help="Kotlin import for a migration symbol; may be repeated")
    parser.add_argument("--database-name", default="MigrationMatrix", help="Prefix for generated test database names")
    parser.add_argument("--output", type=Path, help="Kotlin output file; defaults to stdout")
    parser.add_argument("--report", type=Path, help="Optional JSON file containing selected paths")
    args = parser.parse_args()
    try:
        versions = load_schemas(args.schemas)
        migrations = load_migrations(args.migrations, versions)
        scenarios = build_matrix(versions, migrations)
        source = render_kotlin(scenarios, args.package, args.helper, args.database_name, args.migration_import)
        if args.output:
            args.output.parent.mkdir(parents=True, exist_ok=True)
            args.output.write_text(source, encoding="utf-8", newline="\n")
        else:
            sys.stdout.write(source)
        if args.report:
            args.report.parent.mkdir(parents=True, exist_ok=True)
            payload = {
                "versions": list(versions),
                "scenarioCount": len(scenarios),
                "scenarios": [
                    {"from": item.start, "to": item.end, "path": [edge.symbol for edge in item.migrations]}
                    for item in scenarios
                ],
            }
            args.report.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8", newline="\n")
        return 0
    except MatrixError as error:
        parser.exit(2, f"room-migration-matrix: {error}\n")


if __name__ == "__main__":
    raise SystemExit(main())
