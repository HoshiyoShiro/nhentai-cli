# NHentai CLI

A Python command-line tool for searching, viewing and downloading galleries from
nhentai.net using the official v2 API. Downloads can be saved as PDF, ZIP, or
plain image folders, one at a time or in batches from a text file.

Based on the [NClientV3](https://github.com/maxwai/NClientV3) Android app architecture.

> **18+ only.** This tool accesses adult content. Use it only where legal for you,
> and respect the site's terms of service.

## Features

- **Search** by query and tags (include/exclude), with sort order
- **Lookup** a gallery by its numeric code
- **Metadata**: titles, tags, page count, cover and page URLs (text or JSON)
- **Download** as PDF (default), ZIP, or images, with pages in correct order
- **Batch download** from a text file of codes
- **Random** gallery
- Automatic retries on timeouts and server errors; long titles are shortened to
  stay within Windows path limits

## Requirements

- Python 3.8 or newer
- An nhentai account API key (needed for downloads; optional for browsing)

## Setup

### 1. Clone the repository

```bash
git clone https://github.com/HoshiyoShiro/nhentai-cli.git
cd nhentai-cli
```

### 2. Create a virtual environment

Windows (PowerShell):

```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
```

macOS / Linux:

```bash
python3 -m venv .venv
source .venv/bin/activate
```

### 3. Install

```bash
pip install -e .
```

This installs the dependencies and adds an `nhentai` command to the virtual
environment. If you prefer not to install the package, run
`pip install -r requirements.txt` and replace `nhentai` with
`python nhentai.py` in the examples below.

### 4. Add your API key

Downloads use the official archive endpoint, which requires an API key. See the
[API documentation](https://nhentai.net/api/v2/docs) for how to get one from
your account.

Copy the example config and put your key in it:

```bash
# Windows
copy .env.example .env
# macOS / Linux
cp .env.example .env
```

```ini
NHENTAI_API_KEY=your_api_key_here
```

The key is read from, in order: the `NHENTAI_API_KEY` environment variable, a
`.env` file in the current directory, then `.env` in the project folder.
`.env` is in `.gitignore`; never commit or share it.

### 5. Check it works

```bash
nhentai info 682928
```

## Usage

### Search

```bash
nhentai search "blue archive"
nhentai search --tag "sole female" --tag "full color"
nhentai search "blue archive" --exclude-tag "yaoi" --sort popular-week
nhentai search "blue archive" --page 2 --json
```

Sort options: `date` (default), `popular`, `popular-today`, `popular-week`,
`popular-month`.

### Lookup and info

```bash
nhentai code 682928          # look up a gallery code
nhentai info 682928          # full metadata
nhentai info 682928 --json   # metadata as JSON, including every page URL
```

### Download

```bash
nhentai download 682928                   # PDF + image folder (default)
nhentai download 682928 --zip             # PDF + ZIP
nhentai download 682928 --no-pdf --zip    # ZIP + images
nhentai download 682928 --no-pdf --zip --cleanup  # ZIP only
nhentai download 682928 --cleanup         # PDF only, delete images afterwards
nhentai download 682928 -o ./my_downloads # custom output folder
```

Files are saved to `./downloads` by default, named after the gallery's English
title:

```text
downloads/
├── <title>.pdf
├── <title>.zip          (with --zip)
└── <title>/             (page images, unless --cleanup)
```

### Batch download

Create a UTF-8 text file with one gallery code per line:

```text
# codes.txt — blank lines and anything after # are ignored
682928
682407
683189
```

```bash
nhentai download --file codes.txt
nhentai download --file codes.txt --zip --cleanup
```

Duplicate codes are downloaded only once, so the "Galleries queued" count can be
lower than the number of lines. A failed gallery doesn't stop the batch; failed
codes are listed at the end so you can retry them.

### Random

```bash
nhentai random
nhentai random --json
```

## Global options

These go **before** the command, e.g. `nhentai --delay 2 download --file codes.txt`.

| Option | Default | Description |
|---|---|---|
| `--host` | `nhentai.net` | Use a mirror host |
| `--delay` | `0.5` | Seconds to wait between requests |
| `--user-agent` | built-in | Custom User-Agent header |
| `--debug`, `-d` | off | Print request/response details |

## Troubleshooting

| Problem | Fix |
|---|---|
| `Read timed out` / `Request failed ... retrying` | The site is slow or throttling you. Requests are retried automatically (3 attempts). For large batches, raise `--delay` (e.g. `--delay 2`) and re-run the failed codes. |
| `This endpoint requires a valid API key` | `NHENTAI_API_KEY` is missing or wrong. See [Add your API key](#4-add-your-api-key). |
| `Cloudflare blocked the request` | Wait a while and try again, or lower your request rate with `--delay`. |
| `Gallery not found (404)` | The gallery was removed or the code is wrong. |
| `nhentai: command not found` | Activate the virtual environment, or use `python nhentai.py ...` from the project folder. |

## Project layout

```text
nhentai_cli/
├── api_client.py   # NHentaiAPI: v2 API endpoints, auth, retries, data models
├── downloader.py   # Archive download, extraction, PDF/ZIP conversion
└── cli.py          # Command-line interface (argparse)
nhentai.py          # Run the CLI without installing: python nhentai.py ...
.env.example        # Template for your local .env
```

Optional standalone scripts (not needed for normal use):

- `cookie_helper.py`: test the API with exported browser cookies (`--instructions` for help)
- `firefox_cookie_extract.py`: export nhentai.net cookies from a Firefox profile (Windows)
- `nhentai_scraper.py`: HTML scraper fallback, independent of the API

## License

Apache-2.0 (same as NClientV3)
