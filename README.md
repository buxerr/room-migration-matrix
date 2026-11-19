# room-migration-matrix

Generate Android `MigrationTestHelper` tests for every forward pair of exported Room schema versions. The tool checks graph reachability first, so a missing route fails generation instead of silently leaving an upgrade path untested.

## Why

Room exports each database schema version as JSON, but teams still have to keep migration test cases in sync with those exports and their migration objects. This tool reads the exported versions plus an explicit migration manifest, finds a deterministic shortest path for each old-to-new pair, and writes a compilable Kotlin helper function.

## Install and use

```sh
python -m pip install .
room-migration-matrix \
  --schemas app/schemas \
  --migrations migration-edges.json \
  --package com.example.db \
  --output app/src/androidTest/java/com/example/db/GeneratedMigrationMatrix.kt \
  --report build/migration-matrix.json
```

`migration-edges.json` maps each supported Room version edge to the Kotlin expression for that migration instance:

```json
{
  "migrations": [
    { "from": 1, "to": 2, "symbol": "MIGRATION_1_2" },
    { "from": 2, "to": 3, "symbol": "AppMigrations.MIGRATION_2_3" },
    { "from": 1, "to": 3, "symbol": "MIGRATION_1_3" }
  ]
}
```

The generated file defines `runGeneratedMigrationMatrix(migrationTestHelper)`. Call it from an Android instrumented test that owns a `MigrationTestHelper`; add `--migration-import` for each migration object outside the generated file's package. The helper must load the same exported schema directory used by the app. The generated `createDatabase` and `runMigrationsAndValidate` calls use unique database names for each source/target pair.

This checks path coverage and Room's schema validation. It cannot prove data-preservation behavior; add assertions for important transformed rows to migration tests for those paths. It currently generates upward paths only; Room downgrade behavior needs a separate explicit policy.

## Development

```sh
PYTHONPATH=src python -m unittest discover -s tests -v
```

Install the CLI with `python -m pip install .` in a normal Python environment.

Python 3.10+; runtime has no third-party dependencies. MIT licensed.
