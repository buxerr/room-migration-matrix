# Android Room Migration Test Matrix Generator

Generate Kotlin instrumentation-test code for every forward upgrade path between exported Android Room schema versions. `room-migration-matrix` reads Room schema JSON and an explicit migration graph, checks reachability, and writes a helper that runs those paths with Room's `MigrationTestHelper`.

Use it to keep migration-path coverage aligned with the schema versions your app ships. It complements Room's migration tools; it does not replace Room's migration engine.

## Install and generate a matrix

Requires Python 3.10 or newer. Install from a checkout:

```sh
git clone https://github.com/buxerr/room-migration-matrix.git
cd room-migration-matrix
python -m pip install .
room-migration-matrix \
  --schemas app/schemas \
  --migrations migration-edges.json \
  --package com.example.db \
  --output app/src/androidTest/java/com/example/db/GeneratedMigrationMatrix.kt \
  --report build/migration-matrix.json
```

The migration manifest maps each version edge to the Kotlin expression for its migration object:

```json
{
  "migrations": [
    { "from": 1, "to": 2, "symbol": "MIGRATION_1_2" },
    { "from": 2, "to": 3, "symbol": "AppMigrations.MIGRATION_2_3" },
    { "from": 1, "to": 3, "symbol": "MIGRATION_1_3" }
  ]
}
```

The generated Kotlin defines `runGeneratedMigrationMatrix(migrationTestHelper)`. Call it from an Android instrumented test that owns a `MigrationTestHelper`. Add `--migration-import` for migration objects outside the generated file's package, and configure the helper to load the same exported schemas as the app.

## What the matrix verifies

The generator finds a deterministic shortest route for each old-to-new version pair. A missing route fails generation instead of silently leaving that pair untested. Each generated path uses unique database names and Room's schema validation.

See the [Room migration testing documentation](https://developer.android.com/training/data-storage/room/migrating-db-versions.html) for the underlying helper and migration APIs.

## Scope and limitations

Schema validation does not prove that application data was preserved or transformed correctly. Add row-level assertions for important data changes. This tool generates forward paths only; downgrade testing requires a separate app policy.

Run the Python unit suite with `PYTHONPATH=src python -m unittest discover -s tests -v`.

## License

MIT. See [LICENSE](LICENSE).
