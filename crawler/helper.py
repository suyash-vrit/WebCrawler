from colorama import Fore, Style
from urllib.parse import urlsplit, urlunsplit
from pathlib import Path

DATAPATH_BASE = Path(__file__).parent / "scraped"


class BasicLogger:
    def __init__(self, log_file="logs.txt"):
        self.file_enabled = False
        self.log_file = log_file

    def toggle_file_logging(self):
        self.log_file = not self.log_file
        return self.log_file

    def log_info(self, msg: str):
        info = f"[INFO] {msg}"
        print(Fore.CYAN + info + Style.RESET_ALL)

        if self.file_enabled:
            with open(self.log_file, "a") as lf:
                lf.write(f"{info}\n")

    def log_debug(self, msg: str):
        debug = f"[DEBUG] {msg}"
        print(Fore.YELLOW + debug + Style.RESET_ALL)
        if self.file_enabled:
            with open(self.log_file, "a") as lf:
                lf.write(f"{debug}\n")

    def log_error(self, msg: str):
        error = f"[ERROR] {msg}"
        print(Fore.RED + error + Style.RESET_ALL)
        if self.file_enabled:
            with open(self.log_file, "a") as lf:
                lf.write(f"{error}\n")


def _normalize_url(u: str) -> str:
    """Strip empty fragments and normalize trivial parts."""
    u = u.strip()
    if not u:
        return ""
    parts = urlsplit(u)
    # Drop empty trailing fragment "#"
    if parts.fragment == "":
        parts = parts._replace(fragment="")
    return urlunsplit(parts)


def initialize_seeds_vars(file):
    logger = BasicLogger()
    seeds = []
    seed_vars = []
    try:
        with open(file, "r") as f:
            seeds = f.readlines()
    except FileNotFoundError:
        logger.log_error(f"File {file} not found")

    if seeds:
        for seed in seeds:
            url_split = urlsplit(seed.strip())
            if url_split.netloc and url_split.scheme in ["https", "http"]:
                OUT_DIR = DATAPATH_BASE / f"{url_split.netloc}"
                MD_DIR = OUT_DIR / "md"
                JSONL_PATH = OUT_DIR / "index.jsonl"

                seed_vars.append(
                    {
                        "url": _normalize_url(seed.strip()),
                        "out_dir": OUT_DIR,
                        "md_dir": OUT_DIR / "md",
                        "jsonl_path": JSONL_PATH,
                        "allowed_domain": f"{url_split.netloc}",
                    }
                )

                # directory shenanigans
                OUT_DIR.mkdir(parents=True, exist_ok=True)
                MD_DIR.mkdir(parents=True, exist_ok=True)
                # ensure file exists
                JSONL_PATH.write_text("", encoding="utf-8")

                # logger.log_debug("")
            else:
                logger.log_error(f"{seed} is not a valid URL")
    else:
        logger.log_error(f"{file} doesn't contain any seeds")

    return seed_vars


def initialize_single_url(url):
    logger = BasicLogger()
    url_split = urlsplit(url.strip())
    if url_split.netloc and url_split.scheme in ["https", "http"]:
        OUT_DIR = DATAPATH_BASE / f"{url_split.netloc}_single"
        MD_DIR = OUT_DIR / "md"
        JSONL_PATH = OUT_DIR / "index.jsonl"

        seed = {
            "url": _normalize_url(url.strip()),
            "out_dir": OUT_DIR,
            "md_dir": OUT_DIR / "md",
            "jsonl_path": JSONL_PATH,
            "allowed_domain": f"{url_split.netloc}",
        }

        # directory shenanigans
        OUT_DIR.mkdir(parents=True, exist_ok=True)
        MD_DIR.mkdir(parents=True, exist_ok=True)
        # ensure file exists
        JSONL_PATH.write_text("", encoding="utf-8")
        return seed
    else:
        logger.log_error(f"{url} is not a valid URL")


def chunk_markdown(md: str, target_chars: int = 1200):
    """Simple char-based chunker on paragraph boundaries."""
    paragraphs = [p.strip() for p in md.split("\n\n") if p.strip()]
    chunks, buf, count = [], [], 0
    for p in paragraphs:
        buf.append(p)
        count += len(p)
        if count >= target_chars:
            chunks.append("\n\n".join(buf))
            buf, count = [], 0
    if buf:
        chunks.append("\n\n".join(buf))
    return chunks


def count_block_signals(results) -> float:
    """
    Estimate fraction of "blocked" pages using typical signals:
    - HTTP 429 (Too Many Requests)
    - HTTP 403 (Forbidden)
    - Empty/None markdown on a page that otherwise returned 2xx
    """
    if not results:
        return 0.0
    total = 0
    blocked = 0.0
    for r in results:
        if not r:
            continue
        total += 1
        status = getattr(r, "http_status", None)
        md = getattr(r, "markdown", None)

        if status and status // 100 == 4:
            blocked += 1.0
        elif status and 200 <= status < 300 and (not md or not md.strip()):
            blocked += 0.5  # soft signal
    if total == 0:
        return 0.0
    return blocked / float(total)
