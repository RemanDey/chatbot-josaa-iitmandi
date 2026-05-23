import unittest
from unittest.mock import MagicMock, patch
import os
import sys
from pathlib import Path

# Ensure project root is in path
sys.path.append(str(Path(__file__).resolve().parent.parent))

from app.config import settings
from app.generator import generate_answer


class TestProductionGenerator(unittest.TestCase):
    def setUp(self):
        # Set up keys and temperature
        settings.groq_api_key = "test-groq-key"
        settings.openrouter_api_key = "test-openrouter-key"
        settings.temperature = 0.0

    @patch("httpx.Client")
    def test_successful_groq_generation(self, mock_client_class):
        # Setup mock client
        mock_client = MagicMock()
        mock_client_class.return_value.__enter__.return_value = mock_client
        
        # Mock successful Groq response
        mock_response = MagicMock()
        mock_response.json.return_value = {
            "choices": [{"message": {"content": "This is a response from Groq. [1]"}}]
        }
        mock_client.post.return_value = mock_response

        # Sample input chunks
        chunks = [
            {
                "text": "IIT Mandi was established in 2009.",
                "confidence_score": 0.85,
                "metadata": {"source": "handbook.pdf"}
            }
        ]

        result = generate_answer("When was IIT Mandi established?", chunks)

        # Assertions
        self.assertIsNotNone(result)
        self.assertEqual(result["answer"], "This is a response from Groq. [1]")
        self.assertEqual(result["confidence"], 0.85)
        self.assertEqual(result["sources"][0]["source"], "handbook.pdf")
        
        # Verify Groq was called with correct model
        mock_client.post.assert_called_once()
        call_args = mock_client.post.call_args[1]
        self.assertEqual(call_args["json"]["model"], "llama-3.3-70b-versatile")

    @patch("httpx.Client")
    def test_fallback_to_openrouter(self, mock_client_class):
        # Setup mock client
        mock_client = MagicMock()
        mock_client_class.return_value.__enter__.return_value = mock_client
        
        # Setup post to raise exception for first call (Groq) and succeed for second (OpenRouter)
        mock_response = MagicMock()
        mock_response.json.return_value = {
            "choices": [{"message": {"content": "This is a response from OpenRouter. [1]"}}]
        }
        mock_client.post.side_effect = [Exception("Groq error"), mock_response]

        # Sample input chunks
        chunks = [
            {
                "text": "IIT Mandi is in Himachal Pradesh.",
                "confidence_score": 0.90,
                "metadata": {"source": "general.txt"}
            }
        ]

        result = generate_answer("Where is IIT Mandi located?", chunks)

        # Assertions
        self.assertEqual(result["answer"], "This is a response from OpenRouter. [1]")
        self.assertEqual(result["confidence"], 0.90)
        self.assertEqual(result["sources"][0]["source"], "general.txt")
        
        # Verify post was called twice
        self.assertEqual(mock_client.post.call_count, 2)

    @patch("httpx.Client")
    def test_confidence_gate_rejection(self, mock_client_class):
        # Chunks below threshold (0.4)
        chunks = [
            {
                "text": "Some text.",
                "confidence_score": 0.35,
                "metadata": {"source": "unknown"}
            }
        ]
        
        result = generate_answer("Query?", chunks)
        
        self.assertEqual(result["answer"], "I don't have enough information to answer this.")
        self.assertEqual(result["confidence"], 0.0)
        self.assertEqual(result["sources"], [])
        
        # Verify no API call was made
        mock_client_class.assert_not_called()

    @patch("httpx.Client")
    def test_both_apis_fail(self, mock_client_class):
        # Setup mock client
        mock_client = MagicMock()
        mock_client_class.return_value.__enter__.return_value = mock_client
        
        # Both calls raise exceptions
        mock_client.post.side_effect = [Exception("Groq failed"), Exception("OpenRouter failed")]

        chunks = [
            {
                "text": "Some verified fact.",
                "confidence_score": 0.80,
                "metadata": {"source": "fact.pdf"}
            }
        ]

        with self.assertRaises(RuntimeError) as context:
            generate_answer("Query?", chunks)

        self.assertIn("Failed to generate answer from both Groq and OpenRouter", str(context.exception))

    @patch("httpx.Client")
    def test_safeguard_refusal(self, mock_client_class):
        # Even with high-confidence chunks
        chunks = [
            {
                "text": "Some curriculum details.",
                "confidence_score": 0.95,
                "metadata": {"source": "curriculum.pdf"}
            }
        ]

        # Query about BTech in Chemical Engineering and Data Analytics
        result = generate_answer("What is the syllabus of Btech in Chemical Engineering and Data Analytics?", chunks)

        # Should immediately return safeguard refusal response without calling API
        self.assertEqual(result["answer"], "Not much information is available for this branch at the moment. It is best to ask a senior or refer to official resources.")
        self.assertEqual(result["confidence"], 0.0)
        self.assertEqual(result["sources"], [])
        mock_client_class.assert_not_called()


if __name__ == "__main__":
    unittest.main()
