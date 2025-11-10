# crawl_seeded.py
# Compatible with Crawl4AI v0.7.x (tested on 0.7.4)

import asyncio
import json
import argparse
import random
import math
import uuid
from pprint import pprint

from crawl4ai import (
    AsyncWebCrawler,
    BrowserConfig,
    AdaptiveConfig,
    AdaptiveCrawler,
    CrawlerRunConfig,
    DefaultMarkdownGenerator,
)
from crawl4ai.deep_crawling import (
    BestFirstCrawlingStrategy,
    BFSDeepCrawlStrategy,
    FilterChain,
)
from crawl4ai.deep_crawling.filters import (
    ContentRelevanceFilter,
    DomainFilter,
    URLPatternFilter,
)
from crawl4ai.content_filter_strategy import BM25ContentFilter, PruningContentFilter
from crawl4ai.deep_crawling.scorers import KeywordRelevanceScorer
from urllib.parse import urlsplit
from pprint import pprint


from config import *
from helper import (
    BasicLogger,
    initialize_seeds_vars,
    count_block_signals,
    initialize_single_url,
)

# ==============================
# Utility Functions
# ==============================


# ALL_SEEDS = initialize_seeds_vars(SEEDS_FILE)
logger = BasicLogger()


def calculate_score(string: str, keywords: list[str]):
    matches = sum(1 for k in keywords if k in string)

    # Fast return paths
    if not matches:
        return 0.0
    if matches == len(keywords):
        return 1.0

    return matches / len(keywords)


class Crawler:
    def __init__(self, seed_dict):
        self.seed_dict = seed_dict
        self.enabled_adaptive_strategy = False
        self.enabled_bfs_strategy = not (Mode.BFS_STRATEGY.value - STRATEGY.value)
        self.enabled_bestfirst_strategy = not (
            Mode.BESTFIRST_STRATEGY.value - STRATEGY.value
        )
        self.pages_crawled = 0
        self.written = 0  # no. of md pages written (for tracking MAX_PAGES limit)
        self.results = []
        self.batch = []
        self.out_dir = seed_dict["out_dir"]
        self.md_dir = seed_dict["md_dir"]
        self.jsonl_path = seed_dict["jsonl_path"]
        self.allowed_domain = seed_dict["allowed_domain"]
        self.blocked_rate = 0
        self.blocked_domains = BLOCKED_DOMAINS
        self.content_relevance_filter_q = CONTENT_RELEVANCE_QUERY
        self.enabled_url_matching = False
        if KEYWORDS:
            self.keyword_scorer = KeywordRelevanceScorer(keywords=KEYWORDS, weight=1)
        else:
            self.keyword_scorer = None

        # Rudimentary Check
        seed = seed_dict["url"]
        if not seed:
            raise SystemExit("seed not accessible")

    def get_adaptive_config(self):
        if self.enabled_adaptive_strategy:
            high_precision_config = AdaptiveConfig(
                confidence_threshold=0.9,  # Very high confidence required
                max_pages=50,  # Allow more pages
                top_k_links=5,  # Follow more links per page
                min_gain_threshold=0.02,  # Lower threshold to continue
            )

            # The following configs aren't accessed currently
            # Balanced configuration (default use case)
            balanced_config = AdaptiveConfig(
                confidence_threshold=0.7,  # Moderate confidence
                max_pages=20,  # Reasonable limit
                top_k_links=3,  # Moderate branching
                min_gain_threshold=0.05,  # Standard gain threshold
            )

            # Quick exploration configuration
            quick_config = AdaptiveConfig(
                confidence_threshold=0.5,  # Lower confidence acceptable
                max_pages=10,  # Strict limit
                top_k_links=2,  # Minimal branching
                min_gain_threshold=0.1,  # High gain required
            )
            return high_precision_config
        else:
            logger.log_error("Adaptive Strategy isn't enabled; no configs returned")
            return None

    def get_filter(self):
        # Configure domain filter only (no URL pattern filtering for now)
        domain_filter = DomainFilter(
            allowed_domains=[self.allowed_domain],
            blocked_domains=self.blocked_domains if self.blocked_domains else [],
        )
        bm25_content_filter = BM25ContentFilter(
            user_query="product pricing feature",
            bm25_threshold=10,
        )
        pruning_filter = PruningContentFilter(
            threshold=0.52,  # Slightly stricter than default
            threshold_type="fixed",
            user_query="product",
        )

        # content_filter = ContentRelevanceFilter(
        #     query=self.content_relevance_filter_q,
        #     threshold=0.6 if self.content_relevance_filter_q else 0,
        # )

        if URL_FILTERS:
            url_filter = URLPatternFilter(
                patterns=URL_FILTERS,
            )

            if BLOCKED_KEYWORDS:
                block_filter = URLPatternFilter(
                    patterns=BLOCKED_KEYWORDS,
                    reverse=True,
                )
                return FilterChain([domain_filter, block_filter, url_filter])

            return FilterChain([domain_filter, url_filter])

        if BLOCKED_KEYWORDS:
            block_filter = URLPatternFilter(
                patterns=BLOCKED_KEYWORDS,
                reverse=True,
            )
            return FilterChain([domain_filter, block_filter])

        return FilterChain([domain_filter])  # , url_filter])

    def get_strategy(self):
        strategy = None
        if self.enabled_bestfirst_strategy:
            if DEBUG:
                logger.log_debug("Using BestFirstStrategy")
            strategy = BestFirstCrawlingStrategy(
                max_pages=MAX_PAGES,
                max_depth=MAX_DEPTH,
                include_external=False,
                url_scorer=self.keyword_scorer if KEYWORDS else None,
                filter_chain=self.get_filter(),
            )
        elif self.enabled_bfs_strategy:
            if DEBUG:
                logger.log_debug("Using BFSStrategy")
            strategy = BFSDeepCrawlStrategy(
                max_depth=MAX_DEPTH,  # Crawl initial page + 2 levels deep
                include_external=False,  # Stay within the same domain
                max_pages=MAX_PAGES,  # Maximum number of pages to crawl (optional)
                score_threshold=(
                    0.1 if KEYWORDS else float(-1 * math.inf)
                ),  # Minimum score for URLs to be crawled (optional)
                url_scorer=self.keyword_scorer if KEYWORDS else None,
                filter_chain=self.get_filter(),
            )

        return strategy

    async def crawl(self, seed):
        # Start with the configured base delay; adjust via backoff if needed
        per_seed_base_delay = BASE_DELAY_SEC

        # for idx, seed in enumerate(seeds, start=1):
        # Jitter per seed (makes crawl tempo less bot-like)
        jitter = random.uniform(DELAY_JITTER_MIN, DELAY_JITTER_MAX)
        per_seed_delay = min(per_seed_base_delay + jitter, BACKOFF_MAX_DELAY)

        # Conservative concurrency (per seed)
        concurrency = BASE_CONCURRENCY

        # --- Browser configuration (clean session per seed) ---
        browser_cfg = BrowserConfig(
            headless=True,
            verbose=True,
            java_script_enabled=True,  # Enable JavaScript in browser
            enable_stealth=True,
            user_agent=(
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/120.0.0.0 Safari/537.36"
            ),
            browser_mode="pool",
            sleep_on_close=True,
        )

        # --- Crawler run configuration ---
        run_cfg = CrawlerRunConfig(
            # cache_mode=CacheMode.ENABLED,
            check_robots_txt=False,
            page_timeout=REQUEST_TIMEOUT_SEC * 1000,  # Convert to milliseconds
            mean_delay=per_seed_delay,  # Use mean_delay instead of delay
            excluded_tags=["script", "style"],  # Exclude script tags if needed
            remove_overlay_elements=False,
            markdown_generator=DefaultMarkdownGenerator(
                options={"links_as_footnotes": False, "wrap_tables": True},
            ),
            verbose=True,
            # Additional parameters to handle dynamic content
            wait_until="domcontentloaded",  # Wait for DOM to load
            delay_before_return_html=1,  # Small delay before capturing HTML
            # Configure deep crawling strategy
            deep_crawl_strategy=self.get_strategy(),
            scan_full_page=True,
        )

        logger.log_info(f"Strategy: {self.get_strategy()}")

        print(f"[Seed X] {seed} | delay={per_seed_delay:.2f}s | conc={concurrency}")
        target_pages = MAX_PAGES

        async with AsyncWebCrawler(config=browser_cfg) as crawler:

            self.batch = await crawler.arun(
                url=seed,
                config=run_cfg,
            )


            if not isinstance(self.batch, list):
                self.batch = [self.batch] if self.batch else []

            # for r in self.batch:
            #     if calculate_score(r.url, KEYWORDS) != 1:
            #         logger.log_info(f"SCORE: {calculate_score(r.url, KEYWORDS)}")
            #         continue

        # Backoff heuristic: if we see many 429/403/empty, slow down future seeds
        self.blocked_rate = count_block_signals(self.batch)
        if self.blocked_rate >= BACKOFF_THRESHOLD_RATE:
            print(
                f"  -> Block signals high ({self.blocked_rate:.0%}). Backing off."
            )
            per_seed_base_delay = min(
                per_seed_base_delay * BACKOFF_MULTIPLIER, BACKOFF_MAX_DELAY
            )
        else:
            # slowly relax (optional): keep it steady to be safe
            pass


        # Save outputs - filter out unwanted file types at processing level
        self.save_json()
        self.results.extend(self.batch)
        print(f"Done. Total pages saved: {self.pages_crawled}. Output: {self.out_dir}")

    def save_json(self):
        with open(self.jsonl_path, "a", encoding="utf-8") as jf:
            for r in self.batch:
                if not r or not getattr(r, "markdown", None):
                    continue

                if KEYWORDS:
                    if calculate_score(r.url, KEYWORDS) != 1:
                        logger.log_info(f"SCORE: {calculate_score(r.url, KEYWORDS)}")
                        continue

                url_lower = r.url.lower()

                if DEBUG:
                    print(url_lower)

                skip_extensions = [
                    ".pdf",
                    ".zip",
                    ".rar",
                    ".7z",
                    ".jpg",
                    ".jpeg",
                    ".png",
                    ".gif",
                    ".svg",
                    ".webp",
                    ".bmp",
                    ".mp4",
                    ".webm",
                    ".avi",
                    ".mp3",
                    ".wav",
                ]
                if any(url_lower.endswith(ext) for ext in skip_extensions):
                    continue
                if urlsplit(r.url).path:
                    safe = (
                        urlsplit(r.url)
                        .path.replace("https://", "")
                        .replace("http://", "")
                        .replace("/", "*")
                        .replace("?", "%3F")
                        .replace("#", "%23")
                    )
                else:
                    safe = (
                        r.url.replace("https://", "")
                        .replace("http://", "")
                        .replace("/", "_")
                        .replace("?", "%3F")
                        .replace("#", "%23")
                    )
                if DEBUG:
                    pprint(r.markdown)
                # try:
                #     page_md_path = self.md_dir / f"{safe}.md"
                #     page_md_path.write_text(r.markdown, encoding="utf-8")
                # except:
                #     page_md_path = self.md_dir / f"{safe[:50]}.md"
                #     page_md_path.write_text(r.markdown, encoding="utf-8")

                ########## Path-like Directory Saving ###################
                # parsed = urlparse(r.url)
                # domain = parsed.netloc.replace("www.", "")
                # path = parsed.path or "/"
                # clean_path = re.sub(r"^/|/$", "", path)
                # clean_path = re.sub(r"[<>|:*?\"\\]", "", clean_path)
                # safe_name = f"{domain}_{clean_path}".strip("_")
                # if not safe_name or safe_name.endswith("."):
                #     safe_name = f"{domain}_index"
                # safe_name = safe_name[:200]  # Prevent too-long names

                # if DEBUG:
                #     pprint(r.markdown)

                page_md_path = self.md_dir / f"{safe}_{str(uuid.uuid4())}.md"
                try:
                    page_md_path.parent.mkdir(parents=True, exist_ok=True)
                    page_md_path.write_text(r.markdown, encoding="utf-8")
                except Exception as e:
                    print(f"Failed to write {page_md_path}: {e}")
                    safe_name = safe[:42] + "_" + str(uuid.uuid4())
                    page_md_path = self.md_dir / f"{safe_name}.md"
                    page_md_path.write_text(r.markdown, encoding="utf-8")

                rec = {
                    "url": r.url,
                    "status": getattr(r, "http_status", None),
                    "title": getattr(r, "title", None),
                    "path_md": str(page_md_path.as_posix()),
                }

                jf.write(json.dumps(rec, ensure_ascii=False) + "\n")

                self.written += 1
                self.pages_crawled += 1

            print(
                f"  -> Seed wrote {self.written} pages (total so far: {self.pages_crawled})."
            )

            # Respect a seed pause with jitter (looks more human, reduces burstiness)
            # if idx < len(seeds):
            pause = random.uniform(SEED_PAUSE_MIN_SEC, SEED_PAUSE_MAX_SEC)
            if self.blocked_rate >= BACKOFF_THRESHOLD_RATE:
                pause *= 1.5

            print(f"  -> Sleeping {pause:.1f}s before next seed…")

            # await asyncio.sleep(pause)

            # self.results.extend(self.batch)


async def run_scraper():
    if not ALL_SEEDS:
        print("No valid seeds found.")
        return

    semaphore = asyncio.Semaphore(BASE_CONCURRENCY)

    async def sem_crawl(seed_dict):
        async with semaphore:
            crawler_instance = Crawler(seed_dict)
            try:
                print("Crawling...")
                await crawler_instance.crawl(seed_dict["url"])
                # await crawler_instance.save_json()
            except Exception as e:
                logger.log_error(f"Failed crawling {seed_dict['url']}: {e}")

    print(
        f"Starting crawl of {len(ALL_SEEDS)} seeds with concurrency={BASE_CONCURRENCY}"
    )
    await asyncio.gather(*(sem_crawl(seed) for seed in ALL_SEEDS))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="crawl4ai crawler for OrbitChat RAG model",
        formatter_class=argparse.RawTextHelpFormatter,
    )
    # group = parser.add_mutually_exclusive_group(required=False)
    parser.add_argument("-u", "--url", help="Single website URL to crawl")
    parser.add_argument("-p", "--prioritize", help="Keyword list to prioritize")
    parser.add_argument(
        "-s", "--seedfile", help="seeds.txt relative path to scrape from"
    )
    parser.add_argument(
        "-d",
        "--depth",
        help="Depth for crawling; 0 -> only given page; 1 -> +1 hop..",
        type=int,
    )
    parser.add_argument(
        "-m", "--maxpages", help="Max pages per seed for limiting crawling", type=int
    )
    parser.add_argument(
        "-b",
        "--blocked",
        help="Space separated string of Domains to avoid scraping",
    )
    parser.add_argument(
        "-up",
        "--urlpattern",
        help="Space Separated keywords to look for in the URL",
    )
    parser.add_argument(
        "-bp",
        "--blockedpattern",
        help="Space Separated keywords to avoid in the URL",
    )
    args = parser.parse_args()

    if args.seedfile and not args.url:
        SEEDS_FILE = args.seedfile

    if args.url:
        if len(args.url.split(" ")) == 1:
            ALL_SEEDS = [initialize_single_url(args.url)]
            pprint(ALL_SEEDS)
        else:
            ALL_SEEDS = args.url.split(" ")
    else:
        ALL_SEEDS = initialize_seeds_vars(SEEDS_FILE)

    # The following flag is for matching content based on the given KEYWORDS
    #   Uses a simple scoring algorithm, however, hasn't been implemented properly
    if args.prioritize:
        # CONTENT_RELEVANCE_QUERY = args.prioritize
        priority_list = [a.strip() for a in str(args.prioritize).split(" ")]

        if priority_list:
            KEYWORDS = priority_list
            print(KEYWORDS)

    if args.depth is not None:
        MAX_DEPTH = args.depth

    if args.maxpages is not None:
        MAX_PAGES = args.maxpages

    if args.blocked is not None:
        BLOCKED_DOMAINS = args.blocked.split(" ")

    if args.urlpattern:
        patterns = args.urlpattern.lower().strip().split(" ")
        KEYWORDS = patterns
        for p in patterns:
            URL_FILTERS.append(
                f"*{p}*"
            )  # Convert the keywords into a wild-card pattern
        # print(KEYWORDS)
        # print(URL_FILTERS)

    if args.blockedpattern:
        patterns = args.blockedpattern.lower().strip().split(" ")
        for p in patterns:
            BLOCKED_KEYWORDS.append(
                f"*{p}*"
            )  # Convert the keywords into a wild-card pattern

    if not (args.urlpattern or args.blockedpattern):
        STRATEGY = Mode.BFS_STRATEGY

    if not args.seedfile:
        BASE_CONCURRENCY = 1

    try:
        asyncio.run(run_scraper())
    except KeyboardInterrupt:
        print("\nCancelled by user.")
