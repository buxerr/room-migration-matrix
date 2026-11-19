import json
from pathlib import Path
import tempfile
import unittest

from room_migration_matrix.core import Migration, MatrixError, build_matrix, load_migrations, load_schemas, render_kotlin


class MatrixTests(unittest.TestCase):
    def test_chooses_shortest_path_and_covers_every_forward_pair(self):
        versions = [1, 2, 3, 4]
        edges = [
            Migration(1, 2, "M12"), Migration(2, 3, "M23"), Migration(3, 4, "M34"),
            Migration(1, 3, "M13"), Migration(2, 4, "M24"), Migration(1, 4, "M14"),
        ]
        cases = build_matrix(versions, edges)
        self.assertEqual(len(cases), 6)
        paths = {(case.start, case.end): [edge.symbol for edge in case.migrations] for case in cases}
        self.assertEqual(paths[(1, 4)], ["M14"])
        self.assertEqual(paths[(1, 3)], ["M13"])
        self.assertEqual(paths[(2, 4)], ["M24"])

    def test_deterministic_tie_break(self):
        cases = build_matrix([1, 2, 3, 4], [
            Migration(1, 2, "A12"), Migration(2, 3, "A23"), Migration(2, 4, "A24"),
            Migration(1, 3, "B13"), Migration(3, 4, "B34"),
        ])
        case = next(item for item in cases if (item.start, item.end) == (1, 4))
        self.assertEqual([edge.symbol for edge in case.migrations], ["A12", "A24"])

    def test_fails_on_missing_paths_and_invalid_edges(self):
        with self.assertRaisesRegex(MatrixError, "no migration path"):
            build_matrix([1, 2, 3], [Migration(1, 2, "M12")])
        with self.assertRaisesRegex(MatrixError, "invalid migration edge"):
            build_matrix([1, 2], [Migration(2, 1, "M21")])
        with self.assertRaisesRegex(MatrixError, "duplicate migration edge"):
            build_matrix([1, 2], [Migration(1, 2, "A"), Migration(1, 2, "B")])

    def test_loads_room_schema_exports_and_rejects_duplicate_version(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            for version in (1, 2):
                schema = root / "app" / f"{version}.json"
                schema.parent.mkdir(parents=True, exist_ok=True)
                schema.write_text(json.dumps({"formatVersion": 1, "database": {"version": version}}))
            self.assertEqual(load_schemas(root), (1, 2))
            (root / "duplicate.json").write_text(json.dumps({"database": {"version": 2}}))
            with self.assertRaisesRegex(MatrixError, "duplicate Room schema version"):
                load_schemas(root)

    def test_loads_migration_manifest_and_rejects_bad_symbol(self):
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "migrations.json"
            path.write_text(json.dumps({"migrations": [{"from": 1, "to": 2, "symbol": "MIGRATION_1_2"}]}))
            self.assertEqual(load_migrations(path, [1, 2]), (Migration(1, 2, "MIGRATION_1_2"),))
            path.write_text(json.dumps({"migrations": [{"from": 1, "to": 2, "symbol": "x; deleteEverything()"}]}))
            with self.assertRaisesRegex(MatrixError, "invalid Kotlin migration expression"):
                load_migrations(path, [1, 2])

    def test_rendered_cases_use_unique_db_names_and_migration_expressions(self):
        scenarios = build_matrix([1, 2, 3], [Migration(1, 2, "db.M12"), Migration(2, 3, "M23")])
        source = render_kotlin(scenarios, "example.migrations", helper="helper", imports=["example.db.MIGRATION_1_2"])
        self.assertIn("package example.migrations", source)
        self.assertIn('helper.createDatabase("MigrationMatrix_1_3", 1).close()', source)
        self.assertIn("helper.runMigrationsAndValidate(\"MigrationMatrix_1_3\", 3, true, db.M12, M23).close()", source)
        self.assertIn("fun runGeneratedMigrationMatrix(helper: MigrationTestHelper)", source)
        self.assertIn("import example.db.MIGRATION_1_2", source)
        self.assertEqual(source.count("runMigrationsAndValidate"), 3)
        with self.assertRaisesRegex(MatrixError, "invalid Kotlin package"):
            render_kotlin(scenarios, "bad;package")


if __name__ == "__main__":
    unittest.main()
