import json
import os
import unittest
from unittest.mock import patch, MagicMock
from urllib.error import HTTPError, URLError

from app.messenger_sender import (
    MessengerSendError,
    MessengerDeliveryUnknown,
    send_messenger_message,
)


class TestMessengerSender(unittest.TestCase):

    @patch.dict(os.environ, {
        "MESSENGER_OUTBOUND_ENABLED": "false",
        "MESSENGER_PAGE_ACCESS_TOKEN": "test-token",
    })
    @patch("app.messenger_sender.urllib.request.urlopen")
    def test_disabled(self, urlopen):
        with self.assertRaises(MessengerSendError):
            send_messenger_message("123", "456", "Hola")

        urlopen.assert_not_called()

    @patch.dict(os.environ, {
        "MESSENGER_OUTBOUND_ENABLED": "true",
        "MESSENGER_PAGE_ACCESS_TOKEN": "test-token",
    })
    @patch("app.messenger_sender.urllib.request.urlopen")
    def test_success(self, urlopen):
        response = MagicMock()
        response.read.return_value = json.dumps({
            "message_id": "mid.test123"
        }).encode()

        urlopen.return_value.__enter__.return_value = response

        result = send_messenger_message(
            "123", "456", "Hola desde OmniAgent"
        )

        self.assertEqual(result, "mid.test123")
        self.assertEqual(urlopen.call_count, 1)

        request = urlopen.call_args.args[0]
        self.assertEqual(request.get_method(), "POST")

        payload = json.loads(request.data)
        self.assertEqual(payload["recipient"]["id"], "456")
        self.assertEqual(payload["message"]["text"], "Hola desde OmniAgent")

    @patch.dict(os.environ, {
        "MESSENGER_OUTBOUND_ENABLED": "true",
        "MESSENGER_PAGE_ACCESS_TOKEN": "test-token",
    })
    @patch("app.messenger_sender.urllib.request.urlopen")
    def test_http_error(self, urlopen):
        urlopen.side_effect = HTTPError(
            "https://graph.facebook.com",
            403,
            "Forbidden",
            {},
            None,
        )

        with self.assertRaises(MessengerSendError):
            send_messenger_message("123", "456", "Hola")

    @patch.dict(os.environ, {
        "MESSENGER_OUTBOUND_ENABLED": "true",
        "MESSENGER_PAGE_ACCESS_TOKEN": "test-token",
    })
    @patch("app.messenger_sender.urllib.request.urlopen")
    def test_network_error(self, urlopen):
        urlopen.side_effect = URLError("Connection failed")

        with self.assertRaises(MessengerDeliveryUnknown):
            send_messenger_message("123", "456", "Hola")

    @patch.dict(os.environ, {
        "MESSENGER_OUTBOUND_ENABLED": "true",
        "MESSENGER_PAGE_ACCESS_TOKEN": "test-token",
    })
    @patch("app.messenger_sender.urllib.request.urlopen")
    def test_invalid_recipient(self, urlopen):
        with self.assertRaises(MessengerSendError):
            send_messenger_message("123", "invalid-psid", "Hola")

        urlopen.assert_not_called()


if __name__ == "__main__":
    unittest.main()
