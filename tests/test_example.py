import unittest
from src.llm_client import LLMClient
from src.signal_handler import SignalHandler

class TestLLMClient(unittest.TestCase):
    def setUp(self):
        self.client = LLMClient()

    def test_send_request(self):
        response = self.client.send_request("Test input")
        self.assertIsNotNone(response)
        self.assertIn("output", response)

class TestSignalHandler(unittest.TestCase):
    def setUp(self):
        self.client = LLMClient()
        self.handler = SignalHandler(self.client)

    def test_process_message(self):
        response = self.handler.process_message("Hello")
        self.assertIsNotNone(response)
        self.assertEqual(response, "Expected response based on input")

if __name__ == '__main__':
    unittest.main()