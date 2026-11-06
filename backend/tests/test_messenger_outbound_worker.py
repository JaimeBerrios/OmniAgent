import unittest
from unittest.mock import MagicMock, patch
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

from app import messenger_outbound_worker as worker


class TestMessengerOutboundWorker(unittest.TestCase):

    def test_outbound_disabled_by_default(self):
        self.assertFalse(worker.OUTBOUND_ENABLED)

    def test_customer_service_window_open(self):
        db = MagicMock()
        db.scalar.return_value = datetime.now(timezone.utc) - timedelta(hours=1)

        self.assertTrue(
            worker.is_customer_service_window_open(db, 1, 5)
        )

    def test_customer_service_window_expired(self):
        db = MagicMock()
        db.scalar.return_value = datetime.now(timezone.utc) - timedelta(hours=25)

        self.assertFalse(
            worker.is_customer_service_window_open(db, 1, 5)
        )

    def test_customer_service_window_without_messages(self):
        db = MagicMock()
        db.scalar.return_value = None

        self.assertFalse(
            worker.is_customer_service_window_open(db, 1, 5)
        )

    @patch.object(worker, "send_messenger_message")
    @patch.object(worker, "finish_delivery")
    @patch.object(worker, "is_delivery_authorized", return_value=True)
    @patch.object(worker, "is_customer_service_window_open", return_value=False)
    @patch.object(worker, "SessionLocal")
    def test_expired_window_prevents_send(
        self, session, window, authorized, finish, send
    ):
        db = session.return_value.__enter__.return_value

        message = SimpleNamespace(
            id=10, conversation_id=5, direction="outbound"
        )
        conversation = SimpleNamespace(
            id=5, customer_id=8, channel="messenger"
        )
        customer = SimpleNamespace(
            id=8, external_id="fb:123:456"
        )
        page = SimpleNamespace(
            page_id="123", is_active=True
        )

        db.scalar.side_effect = [
            message, conversation, customer, page
        ]

        delivery = {
            "id": 1,
            "message_id": 10,
            "tenant_id": 1,
            "page_id": "123",
            "psid": "456",
            "content": "Hola",
            "token": "test-token",
        }

        worker.process_delivery(delivery)

        send.assert_not_called()
        finish.assert_called_once()
        self.assertEqual(finish.call_args.args[2], "failed")


if __name__ == "__main__":
    unittest.main()


class TestMessengerOutboundSecurity(unittest.TestCase):

    def setUp(self):
        self.delivery = {
            "id": 1,
            "message_id": 10,
            "tenant_id": 1,
            "page_id": "123",
            "psid": "456",
            "content": "Hola",
            "token": "test-token",
        }

    def run_delivery(self, external_id, authorized=True):
        with patch.object(worker, "SessionLocal") as session, \
             patch.object(worker, "send_messenger_message") as send, \
             patch.object(worker, "finish_delivery") as finish, \
             patch.object(
                 worker,
                 "is_delivery_authorized",
                 return_value=authorized,
             ), \
             patch.object(
                 worker,
                 "is_customer_service_window_open",
                 return_value=True,
             ):

            db = session.return_value.__enter__.return_value

            db.scalar.side_effect = [
                SimpleNamespace(id=10, conversation_id=5),
                SimpleNamespace(id=5, customer_id=8),
                SimpleNamespace(id=8, external_id=external_id),
                SimpleNamespace(page_id="123", is_active=True),
            ]

            worker.process_delivery(self.delivery)

            return send.call_count, finish.call_args

    def test_wrong_recipient_prevents_send(self):
        calls, result = self.run_delivery("fb:123:999")

        self.assertEqual(calls, 0)
        self.assertEqual(result.args[2], "failed")

    def test_wrong_page_prevents_send(self):
        calls, result = self.run_delivery("fb:999:456")

        self.assertEqual(calls, 0)
        self.assertEqual(result.args[2], "failed")

    def test_unauthorized_delivery_prevents_send(self):
        calls, result = self.run_delivery(
            "fb:123:456",
            authorized=False,
        )

        self.assertEqual(calls, 0)
        self.assertIsNone(result)


class TestMessengerRecovery(unittest.TestCase):

    @patch.object(worker, "SessionLocal")
    def test_interrupted_delivery_becomes_unknown(self, session):
        db = session.begin.return_value.__enter__.return_value

        result = MagicMock()
        result.scalars.return_value.all.return_value = [15]
        db.execute.return_value = result

        recovered = worker.recover_interrupted()

        self.assertEqual(recovered, [15])
        db.execute.assert_called_once()

        statement = db.execute.call_args.args[0]
        params = statement.compile().params

        self.assertEqual(params["status"], "unknown")
        self.assertIsNone(params["claim_token"])

    @patch.object(worker, "SessionLocal")
    def test_claim_only_pending_deliveries(self, session):
        db = session.begin.return_value.__enter__.return_value
        db.scalar.return_value = None

        result = worker.claim_delivery()

        self.assertIsNone(result)

        query = db.scalar.call_args.args[0]
        params = query.compile().params

        self.assertIn("pending", params.values())
