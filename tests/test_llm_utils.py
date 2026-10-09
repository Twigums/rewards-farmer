"""Tests for falling back to backup OpenRouter keys.

OPENROUTER_API_KEY takes a comma separated list. A key OpenRouter refuses for
being spent, limited or revoked hands the request to the next one, and the key
that worked is the one tried first next time. These fake the HTTP calls, so
none of them reach OpenRouter.

	python -m unittest discover -s tests
"""

import json
import os
import sys
import unittest
from unittest import mock

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

import requests

import llm_utils

MESSAGES = [{"role": "user", "content": "anything"}]


def make_response(status, content="a search query"):
	response = requests.Response()
	response.status_code = status
	response.url = "https://openrouter.ai/api/v1/chat/completions"
	response._content = json.dumps({"choices": [{"message": {"content": content}}]}).encode()

	return response


class BackupKeys(unittest.TestCase):

	def setUp(self):
		patches = [
			mock.patch.object(llm_utils, "DEFAULT_LLM_PROVIDER", "openrouter"),
			mock.patch.object(llm_utils, "_active_key_index", 0),
			mock.patch.dict(os.environ, {"OPENROUTER_API_KEY": "key-a, key-b,,key-c"}),
		]

		for patch in patches:
			patch.start()
			self.addCleanup(patch.stop)

	def post_returning(self, *statuses):
		post = mock.patch.object(llm_utils.requests, "post", side_effect=[make_response(s) for s in statuses])
		self.addCleanup(post.stop)

		return post.start()

	@staticmethod
	def keys_used(post):
		return [call.kwargs["headers"]["Authorization"].removeprefix("Bearer ") for call in post.call_args_list]

	def test_keys_are_split_on_commas_and_blanks_dropped(self):
		self.assertEqual(llm_utils._get_llm_api_keys(), ["key-a", "key-b", "key-c"])

	def test_a_single_key_still_works(self):
		post = self.post_returning(200)

		with mock.patch.dict(os.environ, {"OPENROUTER_API_KEY": "only-key"}):
			self.assertEqual(llm_utils.get_llm_response(MESSAGES), "a search query")

		self.assertEqual(self.keys_used(post), ["only-key"])

	def test_no_keys_at_all_is_an_error(self):
		with mock.patch.dict(os.environ, {"OPENROUTER_API_KEY": " , "}):
			with self.assertRaisesRegex(RuntimeError, "OPENROUTER_API_KEY is required"):
				llm_utils.get_llm_response(MESSAGES)

	def test_a_spent_key_hands_over_to_the_next(self):
		for status in sorted(llm_utils.KEY_EXHAUSTED_STATUSES):
			with self.subTest(status=status):
				llm_utils._active_key_index = 0
				post = self.post_returning(status, 200)

				with self.assertLogs(llm_utils.logger, "WARNING") as logs:
					self.assertEqual(llm_utils.get_llm_response(MESSAGES), "a search query")

				self.assertEqual(self.keys_used(post), ["key-a", "key-b"])
				self.assertIn(f"key 1/3 was refused (HTTP {status})", logs.output[0])
				self.assertNotIn("key-a", logs.output[0])

	def test_the_key_that_worked_is_tried_first_next_time(self):
		post = self.post_returning(402, 200, 200)

		with self.assertLogs(llm_utils.logger, "WARNING"):
			llm_utils.get_llm_response(MESSAGES)
		llm_utils.get_llm_response(MESSAGES)

		self.assertEqual(self.keys_used(post), ["key-a", "key-b", "key-b"])

	def test_the_last_key_wraps_round_to_the_first(self):
		llm_utils._active_key_index = 2
		post = self.post_returning(429, 200)

		with self.assertLogs(llm_utils.logger, "WARNING"):
			llm_utils.get_llm_response(MESSAGES)

		self.assertEqual(self.keys_used(post), ["key-c", "key-a"])
		self.assertEqual(llm_utils._active_key_index, 0)

	def test_every_key_spent_raises_after_one_try_each(self):
		post = self.post_returning(402, 429, 401)

		with self.assertLogs(llm_utils.logger, "WARNING"):
			with self.assertRaises(requests.HTTPError) as raised:
				llm_utils.get_llm_response(MESSAGES)

		self.assertEqual(raised.exception.response.status_code, 401)
		self.assertEqual(self.keys_used(post), ["key-a", "key-b", "key-c"])
		self.assertEqual(llm_utils._active_key_index, 0)

	def test_errors_that_are_not_about_the_key_do_not_switch_keys(self):
		post = self.post_returning(500)

		with self.assertRaises(requests.HTTPError):
			llm_utils.get_llm_response(MESSAGES)

		self.assertEqual(self.keys_used(post), ["key-a"])


class LocalEndpoint(unittest.TestCase):
	"""Local endpoints are untouched: one optional key, no list."""

	def test_without_a_key_no_authorization_is_sent(self):
		with mock.patch.object(llm_utils, "DEFAULT_LLM_PROVIDER", "local"), \
				mock.patch.dict(os.environ, {"LOCAL_LLM_API_KEY": ""}), \
				mock.patch.object(llm_utils.requests, "post", return_value=make_response(200)) as post:
			llm_utils.get_llm_response(MESSAGES)

		self.assertNotIn("Authorization", post.call_args.kwargs["headers"])


if __name__ == "__main__":
	unittest.main()
