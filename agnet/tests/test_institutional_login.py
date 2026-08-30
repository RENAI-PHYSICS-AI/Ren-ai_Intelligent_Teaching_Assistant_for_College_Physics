from __future__ import annotations

import sys
import sqlite3
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch


APP_DIR = Path(__file__).resolve().parents[1]
if str(APP_DIR) not in sys.path:
    sys.path.insert(0, str(APP_DIR))

import analytics_db
import storage


class InstitutionalLoginAliasTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.db_path = Path(self.temp_dir.name) / "assistant.db"
        self.storage_patch = patch.object(storage, "DB_FILE", self.db_path)
        self.analytics_patch = patch.object(analytics_db, "DB_PATH", str(self.db_path))
        self.storage_patch.start()
        self.analytics_patch.start()
        storage.init_db()
        analytics_db.init_db()
        analytics_db.upsert_identity_roster(
            [
                {
                    "identity_type": "teacher",
                    "institutional_id": "243120",
                    "real_name": "郭棣",
                }
            ]
        )
        self.account = analytics_db.create_user(
            "DiGuo",
            "correct-password",
            "郭棣",
            "teacher",
            "243120",
            "郭棣",
        )

    def tearDown(self) -> None:
        self.analytics_patch.stop()
        self.storage_patch.stop()
        self.temp_dir.cleanup()

    def test_streamlit_login_accepts_username_and_employee_id(self) -> None:
        expected = (int(self.account["id"]), "DiGuo")
        self.assertEqual(storage.authenticate("DiGuo", "correct-password"), expected)
        self.assertEqual(storage.authenticate("243120", "correct-password"), expected)

    def test_admin_authentication_accepts_employee_id_alias(self) -> None:
        account = analytics_db.authenticate_user("243120", "correct-password")
        self.assertIsNotNone(account)
        self.assertEqual(account["id"], self.account["id"])
        self.assertEqual(account["username"], "DiGuo")

    def test_employee_id_alias_rejects_wrong_password(self) -> None:
        self.assertEqual(storage.authenticate("243120", "wrong-password"), (None, None))
        self.assertIsNone(analytics_db.authenticate_user("243120", "wrong-password"))

    def test_verified_employee_id_is_reserved_from_new_usernames(self) -> None:
        user_id, message = storage.create_user("243120", "another-password")
        self.assertIsNone(user_id)
        self.assertIn("学号或工号", message)
        with self.assertRaisesRegex(ValueError, "学号或工号"):
            analytics_db.create_user("243120", "another-password")

    def test_legacy_identifier_collision_is_rejected_before_password_check(self) -> None:
        salt, password_hash = analytics_db._hash_password("legacy-password")
        connection = sqlite3.connect(self.db_path)
        connection.execute(
            """INSERT INTO users
               (username, display_name, identity_verified, salt, password_salt,
                password_hash, role, created_at, is_active)
               VALUES (?, ?, 0, ?, ?, ?, 'student', datetime('now'), 1)""",
            ("243120", "旧账号", salt, salt, password_hash),
        )
        connection.commit()
        connection.close()

        self.assertEqual(storage.authenticate("243120", "correct-password"), (None, None))
        self.assertEqual(storage.authenticate("243120", "legacy-password"), (None, None))
        self.assertIsNone(analytics_db.authenticate_user("243120", "correct-password"))
        self.assertIsNone(analytics_db.authenticate_user("243120", "legacy-password"))
        self.assertEqual(
            storage.authenticate("DiGuo", "correct-password"),
            (int(self.account["id"]), "DiGuo"),
        )

    def test_employee_id_cannot_be_reused_across_identity_types(self) -> None:
        result = analytics_db.upsert_identity_roster(
            [
                {
                    "identity_type": "student",
                    "institutional_id": "243120",
                    "real_name": "其他用户",
                }
            ]
        )
        self.assertEqual(result["added"], 0)
        self.assertTrue(result["errors"])

    def test_new_roster_id_cannot_shadow_an_existing_username(self) -> None:
        user_id, _ = storage.create_user("765432", "another-password")
        self.assertIsNotNone(user_id)
        result = analytics_db.upsert_identity_roster(
            [
                {
                    "identity_type": "teacher",
                    "institutional_id": "765432",
                    "real_name": "其他教师",
                }
            ]
        )
        self.assertEqual(result["added"], 0)
        self.assertTrue(result["errors"])

    def test_provisions_all_unbound_teachers_with_independent_salts(self) -> None:
        result = analytics_db.upsert_identity_roster(
            [
                {"identity_type": "teacher", "institutional_id": "450001", "real_name": "教师甲"},
                {"identity_type": "teacher", "institutional_id": "450002", "real_name": "教师乙"},
            ]
        )
        self.assertEqual(result["added"], 2)

        created = analytics_db.provision_unbound_teacher_accounts("shared-password")
        self.assertEqual({row["username"] for row in created}, {"450001", "450002"})
        for account in created:
            self.assertEqual(
                storage.authenticate(account["institutional_id"], "shared-password"),
                (account["user_id"], account["username"]),
            )

        connection = sqlite3.connect(self.db_path)
        rows = connection.execute(
            """SELECT salt, password_hash FROM users
               WHERE username IN ('450001', '450002') ORDER BY username"""
        ).fetchall()
        unbound = connection.execute(
            """SELECT COUNT(*) FROM identity_roster
               WHERE institutional_id IN ('450001', '450002')
                 AND bound_user_id IS NULL"""
        ).fetchone()[0]
        connection.close()
        self.assertEqual(unbound, 0)
        self.assertEqual(len({row[0] for row in rows}), 2)
        self.assertEqual(len({row[1] for row in rows}), 2)

    def test_provisioning_rolls_back_every_account_on_conflict(self) -> None:
        result = analytics_db.upsert_identity_roster(
            [
                {"identity_type": "teacher", "institutional_id": "460001", "real_name": "教师甲"},
                {"identity_type": "teacher", "institutional_id": "460002", "real_name": "教师乙"},
            ]
        )
        self.assertEqual(result["added"], 2)
        salt, password_hash = analytics_db._hash_password("legacy-password")
        connection = sqlite3.connect(self.db_path)
        connection.execute(
            """INSERT INTO users
               (username, display_name, identity_verified, salt, password_salt,
                password_hash, role, created_at, is_active)
               VALUES ('460002', '冲突账号', 0, ?, ?, ?, 'student', datetime('now'), 1)""",
            (salt, salt, password_hash),
        )
        connection.commit()
        connection.close()

        with self.assertRaisesRegex(ValueError, "460002"):
            analytics_db.provision_unbound_teacher_accounts("shared-password")

        connection = sqlite3.connect(self.db_path)
        first_account = connection.execute(
            "SELECT id FROM users WHERE username='460001'"
        ).fetchone()
        unbound = connection.execute(
            """SELECT COUNT(*) FROM identity_roster
               WHERE institutional_id IN ('460001', '460002')
                 AND bound_user_id IS NULL"""
        ).fetchone()[0]
        connection.close()
        self.assertIsNone(first_account)
        self.assertEqual(unbound, 2)


if __name__ == "__main__":
    unittest.main()
