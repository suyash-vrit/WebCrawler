# Web Crawler

## Introduction
The web crawler utilizes the `crawl4ai` library, and has a comprehensive list of flags that can be used to tune the parameters like `depth`, `max_pages`, `seeds`, `blocked_domains/paths`, `url_patterns`.


## Running the GUI
```
git clone https://github.com/suyash-vrit/WebCrawler
cd WebCrawler
uv sync
uv run webview_gui/app.py
```

### GUI Screenshot
![ss](https://github.com/suyash-vrit/WebCrawler/blob/main/assets/ss.png)

## Flags
- `--depth` `-d`: Controls the DEPTH of crawling (0 = only the given URL page; 1 = give URL + 1 hop; so on)
- `--maxpages` `-m`: No. of pages to crawl *per seed*
- `--seedfile` `-s`: `.txt` file containing new line separated URLs for crawling (aka seeds)
- `--blocked` `-b`: Space separated string of URLs/URL paths to avoid scraping
- `--urlpattern` `-up`: Space separated string of patterns/keywords to look for in the URL
- `--url` `-u`: Space-separated URLs that act as seeds; can be passed instead of `--seedfile`



## Usage Examples

1. Scrape `https://jeevee.com` and extract the `.md` files for `adidas shoes`

```
uv run crawl_seeded.py --url "https://jeevee.com" -up "adidas shoe" --depth 2 --maxpages 100
```
> Note: Treat the `maxpages` parameter as an optimization parameter (the lower the faster); there's no guarantee that 100 pages containing the `adidas shoe` will be returned (because this tool doesn't have the capacity to find **all** server directories/paths and scrape from them (specialized tools like `dirbuster` ought to be used for this purpose))

2. Scrape `https://nagmani.com.np` for laptops

```
uv run crawl_seeded.py --url "https://nagmani.com.np" --up "laptop product" --depth 3 --maxpages 200
```

## Local Setup/Contributing

### Using `uv` (Recommended)

`uv` is a blazing-fast python package manager written in Rust. Using `uv` should be the norm! *(i love `uv`)*

#### Linux/macOS

##### `uv` installation

```bash
curl -LsSf https://astral.sh/uv/install.sh | sh     # install uv
```
> You may need to restart your shell for `uv` to start working properly

#### Windows

#### `uv` installation

In PowerShell, run:
```powershell
powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"
```

##### Local setup

```bash
git clone https://github.com/suyash-vrit/WebCrawler.git
cd WebCrawler/
uv sync
```


