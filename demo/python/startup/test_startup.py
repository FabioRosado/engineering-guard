import importlib
import os
import tempfile
import unittest


start_index = importlib.import_module(os.environ.get("STARTUP_EXAMPLE", "fixed")).start_index


class StartupTests(unittest.TestCase):
    def test_success_transfers_connection_to_caller(self):
        index, connection = start_index(tempfile.TemporaryFile, lambda _: "ready")
        self.assertEqual(index, "ready")
        self.assertFalse(connection.closed)
        connection.close()
        self.assertTrue(connection.closed)

    def test_closes_connection_on_failed_initialization(self):
        connections = []

        def open_connection():
            connection = tempfile.TemporaryFile()
            connections.append(connection)
            return connection

        def fail_to_load(_):
            raise ValueError("index unavailable")

        try:
            with self.assertRaisesRegex(ValueError, "index unavailable"):
                start_index(open_connection, fail_to_load)
            self.assertTrue(connections[0].closed)
        finally:
            connections[0].close()

    def test_preserves_startup_and_cleanup_errors(self):
        class Connection:
            def close(self):
                raise OSError("close failed")

        def fail_to_load(_):
            raise ValueError("load failed")

        with self.assertRaisesRegex(ValueError, "load failed") as raised:
            start_index(Connection, fail_to_load)
        self.assertIsInstance(raised.exception.__cause__, OSError)
        self.assertEqual(str(raised.exception.__cause__), "close failed")


if __name__ == "__main__":
    unittest.main()
