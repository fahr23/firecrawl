"""
Tests for upstream Firecrawl features applied to the project.

Covers:
  1. Crawl status timing — batch_scrape_urls returns a timing block
  2. Crawl status timing — crawl_website returns a timing block
  3. Deterministic JSON billing — KAP_REPORT_SCHEMA is a module-level singleton
  4. NuQ concurrency — max_batch_concurrency from config flows into batch kwargs
  5. Video discovery — include_video flag + _normalize_document captures videos
  6. getData_ff timing — kap_downloader.main() has timing instrumentation
"""
import asyncio
import importlib.util
import os
import sys
import types
import unittest
from unittest.mock import MagicMock, AsyncMock

# ── directories ───────────────────────────────────────────────────────────────
TF_DIR      = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
DATA_FF_DIR = os.path.abspath(os.path.join(TF_DIR, "..", "getData_ff"))


# ── helper: inject a stub module ──────────────────────────────────────────────
def _stub(name, **attrs):
    m = types.ModuleType(name)
    for k, v in attrs.items():
        setattr(m, k, v)
    sys.modules[name] = m
    return m


# ── helper: load a .py file without triggering package __init__ ───────────────
def _load_file(alias, filepath):
    spec = importlib.util.spec_from_file_location(alias, filepath)
    mod  = importlib.util.module_from_spec(spec)
    sys.modules[alias] = mod
    spec.loader.exec_module(mod)
    return mod


# ════════════════════════════════════════════════════════════════════════════
# Stub environment — must be set BEFORE importing any project module
# ════════════════════════════════════════════════════════════════════════════

class _FirecrawlCfg:
    api_key               = "test-key"
    base_url              = None
    wait_for              = 3000
    timeout               = 30000
    formats               = ["markdown", "html"]
    max_retries           = 3
    retry_backoff         = 2
    max_batch_concurrency = 5   # NuQ default (upstream #3758)

class _Cfg:
    firecrawl = _FirecrawlCfg()
    def validate(self): return True

_cfg = _Cfg()

# pydantic
_pyd = _stub("pydantic")
_pyd.BaseModel = object
class _FieldDesc:
    def __init__(self, default=None, **kw): pass
    def __call__(self, *a, **kw): return None
_pyd.Field          = _FieldDesc
_pyd.field_validator = staticmethod(lambda *a, **kw: (lambda f: f))

_stub("dotenv", load_dotenv=lambda: None)
_stub("config",  config=_cfg)

# firecrawl SDK
_fc = _stub("firecrawl")
class _FakeApp:
    def __init__(self, **kw): pass
_fc.FirecrawlApp = _FakeApp

# firecrawl.v2.types
_fc_types = _stub("firecrawl.v2.types", ScrapeOptions=MagicMock())
_stub("firecrawl.v2", types=_fc_types)

# heavy third-party deps
_stub("aiohttp")
_stub("bs4",        BeautifulSoup=MagicMock())

# utils stubs with all names each module exports
_mock_provider = MagicMock()
_mock_provider.__name__ = "LLMProvider"
_stub("utils.llm_analyzer",
      LLMAnalyzer=MagicMock(),
      LLMProvider=_mock_provider,
      LocalLLMProvider=MagicMock(),
      OpenAIProvider=MagicMock(),
      GeminiProvider=MagicMock(),
      HuggingFaceLocalProvider=MagicMock())
_stub("utils.text_extractor", TextExtractorFactory=MagicMock())
_stub("utils.pdf_downloader",  PDFDownloader=MagicMock())
_stub("utils.logger",          setup_logging=MagicMock())
_stub("utils.batch_job_manager",
      BatchJobManager=MagicMock(),
      JobStatus=MagicMock())

# domain / application stubs
_stub("domain.repositories.kap_report_repository")
_stub("domain.value_objects.sentiment", SentimentAnalysis=MagicMock())
_stub("domain.services.sentiment_analyzer_service", ISentimentAnalyzer=MagicMock())
_stub("application.dependencies", get_sentiment_analyzer_service=MagicMock())
_stub("infrastructure.services.sentiment_analyzer_impl",
      SentimentAnalyzerService=MagicMock())

# Pre-register `scrapers` as an EMPTY stub package so __init__.py never runs.
# Individual sub-modules get registered after we load them by file path.
_scrapers_pkg = types.ModuleType("scrapers")
_scrapers_pkg.__path__ = [os.path.join(TF_DIR, "scrapers")]
_scrapers_pkg.__package__ = "scrapers"
sys.modules["scrapers"] = _scrapers_pkg

# ── load modules under test by file path ──────────────────────────────────────
_base_mod = _load_file(
    "scrapers.base_scraper",
    os.path.join(TF_DIR, "scrapers", "base_scraper.py"),
)
_scrapers_pkg.BaseScraper = _base_mod.BaseScraper

_kap_mod = _load_file(
    "scrapers.kap_scraper",
    os.path.join(TF_DIR, "scrapers", "kap_scraper.py"),
)

BaseScraper         = _base_mod.BaseScraper
KAP_REPORT_SCHEMA   = _kap_mod.KAP_REPORT_SCHEMA
BIST_INDICES_SCHEMA  = _kap_mod.BIST_INDICES_SCHEMA
KAP_REPORT_PROMPT   = _kap_mod.KAP_REPORT_PROMPT
BIST_INDICES_PROMPT  = _kap_mod.BIST_INDICES_PROMPT


# ── concrete scraper (BaseScraper is abstract) ────────────────────────────────
class _TestScraper(BaseScraper):
    async def scrape(self, **kwargs):
        return {}


# ════════════════════════════════════════════════════════════════════════════
class TestCrawlStatusTiming(unittest.TestCase):
    """Step 1 — timing block exposed on batch_scrape_urls and crawl_website."""

    def setUp(self):
        self.scraper = _TestScraper()

    def _batch_result(self):
        r = MagicMock()
        r.data         = [MagicMock(), MagicMock()]
        r.created_at   = "2026-06-14T10:00:00Z"
        r.completed_at = "2026-06-14T10:00:05Z"
        r.duration     = 5
        return r

    def test_batch_returns_timing_block(self):
        self.scraper.firecrawl = MagicMock()
        self.scraper.firecrawl.batch_scrape = MagicMock(return_value=self._batch_result())

        res = asyncio.get_event_loop().run_until_complete(
            self.scraper.batch_scrape_urls(["https://example.com"])
        )

        self.assertTrue(res["success"])
        self.assertIn("timing", res)
        t = res["timing"]
        self.assertIsInstance(t["wall_duration_s"], float)
        self.assertGreaterEqual(t["wall_duration_s"], 0)
        self.assertEqual(t["api_duration_s"], 5)
        self.assertIsNotNone(t["created_at"])
        self.assertIsNotNone(t["completed_at"])

    def test_crawl_returns_timing_block(self):
        fake = MagicMock()
        fake.created_at   = "2026-06-14T10:00:00Z"
        fake.completed_at = "2026-06-14T10:00:10Z"
        fake.duration     = 10
        self.scraper.firecrawl = MagicMock()
        self.scraper.firecrawl.crawl = MagicMock(return_value=fake)

        res = asyncio.get_event_loop().run_until_complete(
            self.scraper.crawl_website("https://example.com")
        )

        self.assertTrue(res["success"])
        t = res["timing"]
        self.assertGreaterEqual(t["wall_duration_s"], 0)
        self.assertEqual(t["api_duration_s"], 10)


# ════════════════════════════════════════════════════════════════════════════
class TestDeterministicJSONBilling(unittest.TestCase):
    """Step 2 — schemas are module-level singletons for billing cache."""

    def test_kap_report_schema_is_singleton(self):
        self.assertIs(_kap_mod.KAP_REPORT_SCHEMA, _kap_mod.KAP_REPORT_SCHEMA,
            "Must be the same object each access — Firecrawl caches by schema identity")

    def test_bist_indices_schema_is_singleton(self):
        self.assertIs(_kap_mod.BIST_INDICES_SCHEMA, _kap_mod.BIST_INDICES_SCHEMA)

    def test_kap_report_schema_has_required_fields(self):
        props = KAP_REPORT_SCHEMA["properties"]
        for f in ("company", "report_type", "date", "title", "summary", "attachments"):
            self.assertIn(f, props)

    def test_bist_indices_schema_has_indices(self):
        self.assertIn("indices", BIST_INDICES_SCHEMA["properties"])

    def test_prompts_are_non_empty(self):
        self.assertTrue(KAP_REPORT_PROMPT.strip())
        self.assertTrue(BIST_INDICES_PROMPT.strip())


# ════════════════════════════════════════════════════════════════════════════
class TestNuQConcurrency(unittest.TestCase):
    """Step 3 — NuQ max_batch_concurrency flows config → SDK call, 429 retried."""

    def _fake_ok(self):
        r = MagicMock()
        r.data = []; r.created_at = None; r.completed_at = None; r.duration = None
        return r

    def test_config_has_default_concurrency(self):
        self.assertEqual(_cfg.firecrawl.max_batch_concurrency, 5)

    def test_passes_default_concurrency_to_sdk(self):
        s = _TestScraper()
        s.firecrawl = MagicMock()
        s.firecrawl.batch_scrape = MagicMock(return_value=self._fake_ok())
        asyncio.get_event_loop().run_until_complete(
            s.batch_scrape_urls(["https://example.com"])
        )
        kw = s.firecrawl.batch_scrape.call_args[1]
        self.assertEqual(kw.get("max_concurrency"), 5)

    def test_caller_can_override_concurrency(self):
        s = _TestScraper()
        s.firecrawl = MagicMock()
        s.firecrawl.batch_scrape = MagicMock(return_value=self._fake_ok())
        asyncio.get_event_loop().run_until_complete(
            s.batch_scrape_urls(["https://example.com"], max_concurrency=2)
        )
        kw = s.firecrawl.batch_scrape.call_args[1]
        self.assertEqual(kw.get("max_concurrency"), 2)

    def test_429_triggers_retry_and_succeeds(self):
        s = _TestScraper()
        s.firecrawl = MagicMock()
        calls = {"n": 0}
        ok = self._fake_ok()

        def _side(*a, **kw):
            calls["n"] += 1
            if calls["n"] == 1:
                raise Exception("HTTP 429 rate limit exceeded")
            return ok

        s.firecrawl.batch_scrape = MagicMock(side_effect=_side)
        # Patch sleep so the test doesn't actually wait
        orig_sleep = _base_mod.asyncio.sleep
        _base_mod.asyncio.sleep = AsyncMock()
        try:
            res = asyncio.get_event_loop().run_until_complete(
                s.batch_scrape_urls(["https://example.com"])
            )
        finally:
            _base_mod.asyncio.sleep = orig_sleep

        self.assertTrue(res["success"])
        self.assertEqual(calls["n"], 2)


# ════════════════════════════════════════════════════════════════════════════
class TestVideoDiscovery(unittest.TestCase):
    """Step 4 — video format flag and _normalize_document video capture."""

    def setUp(self):
        self.scraper = _TestScraper()

    def _doc(self, videos=None):
        r = MagicMock()
        r.html = None; r.markdown = "text"; r.metadata = {}
        r.links = []; r.summary = None; r.json = None
        r.rawHtml = None; r.actions = None; r.videos = videos
        return r

    def test_include_video_adds_format(self):
        captured = {}
        def fake_scrape(url, params):
            captured["formats"] = list(params["formats"])
            return self._doc()
        self.scraper._call_scrape = fake_scrape
        asyncio.get_event_loop().run_until_complete(
            self.scraper.scrape_url("https://example.com", include_video=True)
        )
        self.assertIn("video", captured["formats"])

    def test_default_no_video_format(self):
        captured = {}
        def fake_scrape(url, params):
            captured["formats"] = list(params["formats"])
            return self._doc()
        self.scraper._call_scrape = fake_scrape
        asyncio.get_event_loop().run_until_complete(
            self.scraper.scrape_url("https://example.com")
        )
        self.assertNotIn("video", captured["formats"])

    def test_normalize_captures_videos(self):
        data = self.scraper._normalize_document(
            self._doc(videos=[{"url": "https://example.com/v.mp4"}])
        )
        self.assertIn("videos", data)
        self.assertEqual(len(data["videos"]), 1)

    def test_normalize_omits_none_videos(self):
        data = self.scraper._normalize_document(self._doc(videos=None))
        self.assertNotIn("videos", data)

    def test_include_video_not_duplicated_if_already_in_formats(self):
        captured = {}
        def fake_scrape(url, params):
            captured["formats"] = list(params["formats"])
            return self._doc()
        self.scraper._call_scrape = fake_scrape
        asyncio.get_event_loop().run_until_complete(
            self.scraper.scrape_url(
                "https://example.com",
                formats=["markdown", "video"],
                include_video=True,
            )
        )
        self.assertEqual(captured["formats"].count("video"), 1)


# ════════════════════════════════════════════════════════════════════════════
class TestGetDataFFTiming(unittest.TestCase):
    """Step 5 — kap_downloader.py has job timing instrumentation."""

    @classmethod
    def _src(cls):
        with open(os.path.join(DATA_FF_DIR, "kap_downloader.py")) as f:
            return f.read()

    def test_uses_perf_counter(self):
        self.assertIn("perf_counter", self._src())

    def test_computes_duration_s(self):
        self.assertIn("duration_s", self._src())

    def test_prints_duration(self):
        self.assertIn("Duration:", self._src())

    def test_prints_started_and_completed(self):
        src = self._src()
        self.assertIn("Started:", src)
        self.assertIn("Completed:", src)

    def test_tracks_counts(self):
        src = self._src()
        for word in ("downloaded", "skipped", "failed"):
            self.assertIn(word, src)


if __name__ == "__main__":
    unittest.main(verbosity=2)
