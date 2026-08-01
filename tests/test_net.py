from __future__ import annotations

import unittest

from scripts.net import _validated_network_url


class NetworkBoundaryTests(unittest.TestCase):
    def test_allows_only_fixed_feed_and_ats_api_hosts(self) -> None:
        allowed = (
            "https://raw.githubusercontent.com/example/repository/main/jobs.json",
            "https://boards-api.greenhouse.io/v1/boards/example/jobs",
            "https://api.lever.co/v0/postings/example?mode=json",
            "https://api.ashbyhq.com/posting-api/job-board/example",
            "https://example.wd5.myworkdayjobs.com/wday/cxs/example/careers/jobs",
        )
        for url in allowed:
            with self.subTest(url=url):
                self.assertEqual(_validated_network_url(url), url)

    def test_rejects_cross_origin_private_and_credentialed_requests(self) -> None:
        rejected = (
            "http://raw.githubusercontent.com/example/repository/main/jobs.json",
            "https://raw.githubusercontent.com.evil.example/jobs.json",
            "https://user:password@raw.githubusercontent.com/jobs.json",
            "https://127.0.0.1/latest/meta-data",
            "https://example.wd5.myworkdayjobs.com:8443/jobs",
        )
        for url in rejected:
            with self.subTest(url=url), self.assertRaises(ValueError):
                _validated_network_url(url)


if __name__ == "__main__":
    unittest.main()
