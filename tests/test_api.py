import time
import os
import tempfile
import asyncio
import threading
import unittest
import httpx
from unittest.mock import patch, MagicMock, AsyncMock

# Use an isolated data directory so tests never touch the real printer
# profile, settings, or history.
_TEST_DATA_DIR = tempfile.mkdtemp(prefix="mps-test-")
os.environ["MPS_DATA_DIR"] = _TEST_DATA_DIR

from fastapi.testclient import TestClient
from backend.main import app


class PersistentLoopClient:
    """
    Minimal ASGI test client that runs the app on ONE persistent event loop,
    so background tasks (e.g. the print queue worker) keep making progress
    between requests — unlike starlette's TestClient, which spins up a fresh
    loop per request.
    """

    def __init__(self, app_):
        self.transport = httpx.ASGITransport(app=app_)
        self.loop = asyncio.new_event_loop()
        self.thread = threading.Thread(target=self._run_loop, daemon=True, name="persistent-loop")
        self.thread.start()
        asyncio.run_coroutine_threadsafe(asyncio.sleep(0), self.loop).result(timeout=5)

    def _run_loop(self):
        asyncio.set_event_loop(self.loop)
        self.loop.run_forever()

    def request(self, method, url, **kwargs):
        async def call():
            async with httpx.AsyncClient(transport=self.transport, base_url="http://test") as ac:
                return await ac.request(method, url, **kwargs)
        fut = asyncio.run_coroutine_threadsafe(call(), self.loop)
        return fut.result(timeout=30)

    def get(self, url, **kwargs):
        return self.request("GET", url, **kwargs)

    def post(self, url, **kwargs):
        return self.request("POST", url, **kwargs)

    def delete(self, url, **kwargs):
        return self.request("DELETE", url, **kwargs)


class TestAPIEndpoints(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.client = PersistentLoopClient(app)

    @staticmethod
    def wait_for_job(client, job_id, timeout=15.0):
        """Polls a print job until it reaches a terminal state."""
        deadline = time.time() + timeout
        while time.time() < deadline:
            res = client.get(f"/api/print/jobs/{job_id}")
            if res.status_code != 200:
                break
            status = res.json().get("status")
            if status in ("completed", "failed", "cancelled"):
                return res.json()
            time.sleep(0.02)
        raise AssertionError(f"Job {job_id} did not reach a terminal state within {timeout}s")

    def test_root_and_static(self):
        res = self.client.get("/")
        self.assertEqual(res.status_code, 200)
        self.assertIn("Mini Print Studio", res.text)

    def test_printer_status(self):
        res = self.client.get("/api/printers/status")
        self.assertEqual(res.status_code, 200)
        data = res.json()
        self.assertTrue("connected" in data)

    def test_printer_list(self):
        # Patch the BLE scan so the test is deterministic and does not
        # require a Bluetooth radio. Scan results are real devices only —
        # no mock/virtual entries are ever returned.
        fake_device = {
            "id": "ble-AA:BB:CC:DD:EE:FF",
            "name": "SC03h-TEST",
            "connection_type": "ble",
            "address": "AA:BB:CC:DD:EE:FF",
            "protocol": "iprint",
            "printable_width_px": 384,
            "paper_width_mm": 58,
            "status": "available",
            "rssi": -60,
            "is_default": False
        }
        with patch("backend.services.printer_manager.BLEPrinterAdapter.scan",
                   new=AsyncMock(return_value=[])) as empty_scan:
            res = self.client.get("/api/printers")
            self.assertEqual(res.status_code, 200)
            self.assertEqual(res.json()["printers"], [])

        with patch("backend.services.printer_manager.BLEPrinterAdapter.scan",
                   new=AsyncMock(return_value=[fake_device])):
            res = self.client.get("/api/printers")
            self.assertEqual(res.status_code, 200)
            printers = res.json()["printers"]
            self.assertEqual(len(printers), 1)
            self.assertEqual(printers[0]["connection_type"], "ble")
            self.assertEqual(printers[0]["protocol"], "iprint")

    def test_print_preview_endpoint(self):
        payload = {
            "title": "API Test Document",
            "blocks": [
                {"type": "text", "content": "API Preview Test", "font_size": "large", "align": "center"},
                {"type": "line", "line_style": "solid"},
                {"type": "space", "space_height": 10}
            ],
            "width_px": 384,
            "margin_px": 8
        }
        res = self.client.post("/api/print/preview", json=payload)
        self.assertEqual(res.status_code, 200)
        data = res.json()
        self.assertEqual(data["width_px"], 384)
        self.assertTrue(data["preview_url"].startswith("data:image/png;base64,"))

    def test_export_png_and_pdf(self):
        payload = {
            "title": "Export Test",
            "blocks": [
                {"type": "text", "content": "EXPORT TEST", "font_size": "large", "align": "center"},
                {"type": "line", "line_style": "solid"}
            ]
        }
        res_png = self.client.post("/api/print/export?fmt=png", json=payload)
        self.assertEqual(res_png.status_code, 200)
        self.assertEqual(res_png.headers["content-type"], "image/png")
        self.assertTrue(res_png.content.startswith(b"\x89PNG"))

        res_pdf = self.client.post("/api/print/export?fmt=pdf", json=payload)
        self.assertEqual(res_pdf.status_code, 200)
        self.assertEqual(res_pdf.headers["content-type"], "application/pdf")
        self.assertTrue(res_pdf.content.startswith(b"%PDF"))

    def test_templates_api(self):
        res = self.client.get("/api/templates")
        self.assertEqual(res.status_code, 200)
        templates = res.json()
        self.assertTrue(len(templates) >= 5)

    def test_history_api(self):
        res = self.client.get("/api/history")
        self.assertEqual(res.status_code, 200)
        history = res.json()
        self.assertTrue(isinstance(history, list))

    def test_settings_api(self):
        res = self.client.get("/api/settings")
        self.assertEqual(res.status_code, 200)
        settings = res.json()
        self.assertIn("printer", settings)

    def test_documents_crud(self):
        # Create
        res = self.client.post("/api/documents", json={
            "title": "Test Doc",
            "blocks": [{"type": "text", "content": "Hello", "font_size": "normal"}]
        })
        self.assertEqual(res.status_code, 200)
        doc = res.json()
        self.assertEqual(doc["title"], "Test Doc")
        doc_id = doc["id"]

        # List
        res = self.client.get("/api/documents")
        self.assertEqual(res.status_code, 200)
        self.assertTrue(any(d["id"] == doc_id for d in res.json()))

        # Delete
        res = self.client.delete(f"/api/documents/{doc_id}")
        self.assertEqual(res.status_code, 200)
        res = self.client.get(f"/api/documents/{doc_id}")
        self.assertEqual(res.status_code, 404)

    def test_mock_connect_and_print(self):
        connect = self.client.post("/api/printers/connect", json={
            "printer_id": "mock-printer-01",
            "connection_type": "mock",
            "address": "00:11:22:33:44:55",
            "protocol": "escpos"
        })
        self.assertEqual(connect.status_code, 200)
        self.assertTrue(connect.json()["connected"])

        job = self.client.post("/api/print", json={
            "title": "Mock Print Test",
            "blocks": [
                {"type": "text", "content": "MOCK PRINT TEST", "font_size": "title", "bold": True, "align": "center"},
                {"type": "line", "line_style": "solid"}
            ],
            "width_px": 384,
            "margin_px": 8,
            "copies": 2
        })
        self.assertEqual(job.status_code, 200)
        data = job.json()
        self.assertEqual(data["status"], "queued")

        finished = self.wait_for_job(self.client, data["id"])
        self.assertEqual(finished["status"], "completed")
        self.assertIn("preview_url", finished)

        self.client.post("/api/printers/disconnect")

    def test_print_queue_and_cancel(self):
        connect = self.client.post("/api/printers/connect", json={
            "printer_id": "mock-printer-01",
            "connection_type": "mock",
            "protocol": "escpos"
        })
        self.assertTrue(connect.json()["connected"])

        job = self.client.post("/api/print", json={
            "title": "Cancellable Job",
            "blocks": [{"type": "text", "content": "CANCEL ME", "font_size": "normal"}]
        })
        job_id = job.json()["id"]
        self.assertEqual(job.json()["status"], "queued")

        # Cancel while queued
        res = self.client.post("/api/print/cancel", json={"job_id": job_id})
        self.assertEqual(res.status_code, 200)
        self.assertIn(job_id, res.json()["cancelled_jobs"])

        finished = self.wait_for_job(self.client, job_id)
        self.assertEqual(finished["status"], "cancelled")

        # Queue endpoint works
        res = self.client.get("/api/print/queue")
        self.assertEqual(res.status_code, 200)
        self.assertIn("active_job", res.json())

        self.client.post("/api/printers/disconnect")

    def test_print_without_connection_fails_cleanly(self):
        # Ensure the singleton manager is disconnected before the check
        self.client.post("/api/printers/disconnect")
        res = self.client.post("/api/print", json={
            "title": "Should Fail",
            "blocks": [{"type": "text", "content": "hi", "font_size": "normal"}]
        })
        self.assertEqual(res.status_code, 503)
        self.assertIn("No printer connected", res.json()["detail"])

    def test_history_stats(self):
        res = self.client.get("/api/history/stats")
        self.assertEqual(res.status_code, 200)
        stats = res.json()
        for key in ("total_jobs", "status_counts", "by_type", "est_paper_mm", "today_jobs"):
            self.assertIn(key, stats)
        self.assertTrue(stats["total_jobs"] >= 0)

    def test_template_favorites(self):
        res = self.client.post("/api/templates/simple_note/favorite", json={"favorite": True})
        self.assertEqual(res.status_code, 200)
        self.assertTrue(res.json()["favorite"])

        settings = self.client.get("/api/settings").json()
        self.assertIn("simple_note", settings["app"]["favorite_templates"])

        res = self.client.post("/api/templates/simple_note/favorite", json={"favorite": False})
        self.assertEqual(res.status_code, 200)
        self.assertFalse(res.json()["favorite"])

    def test_csv_batch_labels(self):
        connect = self.client.post("/api/printers/connect", json={
            "printer_id": "mock-printer-01",
            "connection_type": "mock",
            "protocol": "escpos"
        })
        self.assertTrue(connect.json()["connected"])

        res = self.client.post("/api/print/csv", json={
            "csv_text": "Name,SKU,Price\nWidget A,SKU-001,9.99\nWidget B,SKU-002,14.50\n",
            "name_col": 0,
            "sku_col": 1,
            "price_col": 2,
            "has_header": True,
            "copies": 1
        })
        self.assertEqual(res.status_code, 200)
        data = res.json()
        self.assertEqual(data["submitted"], 2)
        self.assertEqual(len(data["job_ids"]), 2)
        for job_id in data["job_ids"]:
            finished = self.wait_for_job(self.client, job_id)
            self.assertEqual(finished["status"], "completed")

        self.client.post("/api/printers/disconnect")

    def test_reprint_blocks_stored(self):
        connect = self.client.post("/api/printers/connect", json={
            "printer_id": "mock-printer-01",
            "connection_type": "mock",
            "protocol": "escpos"
        })
        self.assertTrue(connect.json()["connected"])

        job = self.client.post("/api/print", json={
            "title": "Reprint Test",
            "blocks": [{"type": "text", "content": "REPRINT ME", "font_size": "large", "align": "center"}]
        })
        finished = self.wait_for_job(self.client, job.json()["id"])
        self.assertTrue(finished.get("blocks"))
        self.assertEqual(finished["blocks"][0]["content"], "REPRINT ME")

        self.client.post("/api/printers/disconnect")


if __name__ == "__main__":
    unittest.main()
