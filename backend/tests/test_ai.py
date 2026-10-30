import io
import json
import os
import unittest
from unittest.mock import patch
from urllib.error import HTTPError

from app import ai
from app.extract import _ocr_images
from app.models import Entities


class AgentRouterTests(unittest.TestCase):
    def setUp(self):
        env = patch.dict(os.environ, {"AGENTROUTER_API_KEY": "test-key",
            "AI_PROVIDERS": "agentrouter", "ANTHROPIC_API_KEY": "", "ANTHROPIC_AUTH_TOKEN": "",
            "AGENTROUTER_BASE_URL": "https://example.test/v1/", "AGENTROUTER_MODEL": "test-model"})
        env.start()
        self.addCleanup(env.stop)

    def response(self, content, finish="stop"):
        return io.BytesIO(json.dumps({"choices": [{"finish_reason": finish,
            "message": {"content": content}}]}).encode())

    def test_image_request_and_provider_priority(self):
        with patch.object(ai, "urlopen", return_value=self.response("Offer letter")) as send:
            self.assertEqual(ai.read_images([b"image"], "image/png"), "Offer letter")
        request = send.call_args.args[0]
        payload = json.loads(request.data)
        self.assertEqual(request.full_url, "https://example.test/v1/chat/completions")
        self.assertEqual(payload["model"], "test-model")
        self.assertEqual(payload["messages"][0]["content"][0]["image_url"]["url"],
                         "data:image/png;base64,aW1hZ2U=")

    def test_valid_assessment(self):
        verdict = dict(risk_level="LOW", confidence=80, summary="Verify the employer.",
            red_flags=[], trust_signals=[], company_name=None, job_title=None, country=None)
        with patch.object(ai, "urlopen", return_value=self.response(json.dumps(verdict))):
            result, warning = ai.analyze("Sample", Entities(), [], None)
        self.assertEqual(result.risk_level, "LOW")
        self.assertIsNone(warning)

    def test_groq_to_openrouter_fallback(self):
        with patch.dict(os.environ, {"AI_PROVIDERS": "groq,openrouter", "GROQ_API_KEY": "groq-test",
                                     "OPENROUTER_API_KEY": "openrouter-test"}), \
             patch.object(ai, "urlopen", side_effect=[HTTPError("url", 429, "limited", {}, None),
                                                       self.response("Recovered text")]) as send:
            self.assertEqual(ai.read_images([b"image"], "image/png"), "Recovered text")
            self.assertEqual(ai.provider_name(), "OpenRouter")
        self.assertEqual(send.call_count, 2)
        self.assertIn("api.groq.com", send.call_args_list[0].args[0].full_url)
        self.assertIn("openrouter.ai", send.call_args_list[1].args[0].full_url)
        self.assertEqual(send.call_args_list[1].args[0].get_header("Authorization"), "Bearer openrouter-test")

    def test_groq_batches_all_five_pages(self):
        with patch.dict(os.environ, {"AI_PROVIDERS": "groq", "GROQ_API_KEY": "groq-test"}), \
             patch.object(ai, "urlopen", side_effect=[self.response("Pages 1-3"), self.response("Pages 4-5")]) as send:
            self.assertEqual(ai.read_images([b"image"] * 5, "image/png"), "Pages 1-3\nPages 4-5")
        self.assertEqual([len(json.loads(c.args[0].data)["messages"][0]["content"]) - 1
                          for c in send.call_args_list], [3, 2])

    def test_invalid_assessment_falls_back(self):
        verdict = dict(risk_level="LOW", confidence=80, summary="Verify the employer.",
            red_flags=[], trust_signals=[], company_name=None, job_title=None, country=None)
        with patch.dict(os.environ, {"AI_PROVIDERS": "groq,openrouter", "GROQ_API_KEY": "groq-test",
                                     "OPENROUTER_API_KEY": "openrouter-test"}), \
             patch.object(ai, "urlopen", side_effect=[self.response("{}"), self.response(json.dumps(verdict))]):
            result, warning = ai.analyze("Sample", Entities(), [], None)
        self.assertEqual(result.risk_level, "LOW")
        self.assertIsNone(warning)

    def test_unconfigured_new_providers_do_not_use_old_key(self):
        with patch.dict(os.environ, {"AI_PROVIDERS": "groq,openrouter", "GROQ_API_KEY": "", "OPENROUTER_API_KEY": ""}):
            self.assertFalse(ai.is_enabled())

    def test_invalid_assessment_is_warning(self):
        with patch.object(ai, "urlopen", return_value=self.response('{"risk_level":"UNKNOWN"}')):
            result, warning = ai.analyze("Sample", Entities(), [], None)
        self.assertIsNone(result)
        self.assertIn("invalid assessment", warning)

    def test_http_error_is_safe(self):
        with patch.object(ai, "urlopen", side_effect=HTTPError("url", 401, "secret", {}, None)):
            result, warning = ai.analyze("Sample", Entities(), [], None)
        self.assertIsNone(result)
        self.assertIn("401", warning)
        self.assertIn("AGENTROUTER_API_KEY", warning)
        self.assertNotIn("secret", warning)

    def test_truncated_answer_is_rejected(self):
        with patch.object(ai, "urlopen", return_value=self.response("partial", "length")):
            with self.assertRaises(ai.AIError):
                ai.read_images([b"image"], "image/png")

    def test_ocr_falls_back_on_provider_failure(self):
        from PIL import Image
        image = io.BytesIO()
        Image.new("RGB", (20, 20), "white").save(image, format="PNG")
        with patch.object(ai, "read_images", side_effect=ai.AIError("Unavailable")), \
             patch("app.extract._tesseract_available", return_value=True), \
             patch("pytesseract.image_to_string", return_value="Local OCR text"):
            text, method, warnings = _ocr_images([image.getvalue()], "image/png")
        self.assertEqual(text, "Local OCR text")
        self.assertEqual(method, "tesseract-ocr")
        self.assertIn("read using local Tesseract OCR", warnings[0])

    def test_ocr_without_fallback_preserves_actionable_error(self):
        with patch.object(ai, "read_images", side_effect=ai.AIError("Authentication rejected (401).")), \
             patch("app.extract._tesseract_available", return_value=False):
            text, method, warnings = _ocr_images([b"image"], "image/png")
        self.assertEqual((text, method), ("", "none"))
        self.assertIn("401", warnings[0])


if __name__ == "__main__":
    unittest.main()
