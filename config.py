from enum import Enum

# For dev purposes
DEBUG=True

# ========= USER SETTINGS (SAFE & POLITE) =========
SEEDS_FILE = "seeds.txt"
MAX_DEPTH = 1              # 0 = only seeds; 1 = seeds + 1 hop; 2 = +2 hops
MAX_PAGES = 50            # crawlers runs in concurrent manner, thus, this prolly controls the per-seed max(?)
GLOBAL_MAX_PAGES = 200


# Crawl pacing (conservative)
BASE_CONCURRENCY = 2       # fewer parallel tabs = friendlier
BASE_DELAY_SEC = 1.2       # base delay between requests (polite)
DELAY_JITTER_MIN = 0.6     # per-seed jitter
DELAY_JITTER_MAX = 1.8

# Seed pacing (sleep between seeds to look human & reduce bursts)
SEED_PAUSE_MIN_SEC = 3.0
SEED_PAUSE_MAX_SEC = 7.0

# Backoff behavior when block signals appear (many 429/403 or empty 2xx)
BACKOFF_THRESHOLD_RATE = 0.20   # if >=20% of pages look blocked, back off
BACKOFF_MULTIPLIER = 1.8        # multiply the delay
BACKOFF_MAX_DELAY = 6.0         # cap delay after backoff

REQUEST_TIMEOUT_SEC = 40        # JS-heavy pages may need time
MAX_WORKERS = 7

KEYWORDS = []
BLOCKED_DOMAINS = []


class Mode(Enum):
    BFS_STRATEGY=1
    BESTFIRST_STRATEGY=2
    ADAPTIVE_STRATEGY=2
