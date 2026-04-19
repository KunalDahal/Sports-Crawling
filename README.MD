# spcrawler

`spcrawler` is a Python crawler for finding suspicious sports streaming pages and extracting likely live stream targets such as `m3u8`, `mpd`, `rtmp`, and iframe embeds.

## Repository Layout

The repository root is named `spcrawler`, and the Python source code now lives in `src/`.

```text
spcrawler/
|- pyproject.toml
|- setup.py
|- requirements.txt
|- .env.example
|- test.py
`- src/
   |- __init__.py
   |- log.py
   |- client/
   |- instance/
   `- utils/
```

## Packaging Layout

`pyproject.toml` and `setup.py` should stay in the repository root.

That is still the correct place for them even though the code is under `src/`:

- the repository root is the Python project root
- `src/` contains the package source code
- the packaging files tell `pip` how to expose that source as the `spcrawler` package

This repo is not using a `src/spcrawler/` tree. Instead, the packaging config maps:

- package name: `spcrawler`
- source directory: `src/`

So after installation, imports stay:

```python
from spcrawler import Scraper
from spcrawler.log import get_logger
```

## Requirements

- Python `3.11+`
- MongoDB
- `GEMINI_API_KEY`

Dependencies are kept aligned across:

- `pyproject.toml`
- `setup.py`
- `requirements.txt`

## Installation

Create and activate a virtual environment:

```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
```

Install dependencies:

```powershell
pip install -r requirements.txt
```

Install the package in editable mode from the repository root:

```powershell
pip install -e .
```

Editable install is important here because the package name is `spcrawler` while the source directory is `src/`.

## Environment Variables

Create a `.env` file in the repository root.

Example:

```env
GEMINI_API_KEY=your_api_key_here
MONGO_URI=mongodb://localhost:27017
DB_NAME=sports_scraper
PROXY_URL=
LOG_LEVEL=info
```

`DB_NAME` is the correct key for the current runner and package code.

## Running the Project

The current root-level runner is `test.py`.
It imports directly from `src/`, so you can run it from the repository without first installing the package.

```powershell
python test.py
```

Inside that file, the crawler currently runs with a hardcoded sample keyword:

```python
"RR vs KKR watch free live"
```

Change that value in `test.py` if you want to target a different match or search phrase.

## Package Contents

- `src/client`: LLM client, prompts, and model helpers
- `src/instance`: scraper runtime, stream checks, and proxy handling
- `src/utils`: config, constants, and database helpers
- `src/log.py`: logging setup
- `src/__init__.py`: package exports for `Scraper` and `ProxyManager`

## Summary

The updated structure is:

- root folder name: `spcrawler`
- package metadata files: repository root
- source code: `src/`
- import name after install: `spcrawler`

That setup is now reflected in the packaging files and the environment example.
