# Profi Scout

A Selenium-powered bot that watches [Profi.ru](https://profi.ru) for new client orders and forwards the ones that match your keywords straight to Telegram — so you never have to keep the tab open and refresh it yourself.

![Python](https://img.shields.io/badge/python-3.9%2B-blue)
![Selenium](https://img.shields.io/badge/selenium-4.x-43B02A)
![License: MIT](https://img.shields.io/badge/license-MIT-green)

## How it works

1. A headless Chrome session (via Selenium) logs into your Profi.ru account using a saved cookie session.
2. It periodically scrolls the orders feed and scrapes new task cards.
3. Each task is checked against a `good_words` / `bad_words` keyword filter you configure.
4. Matching tasks are formatted and sent to a Telegram chat via a bot, in batches, on an interval.
5. Seen/sent tasks and cleanup of stale entries are persisted to a local `state.json` so nothing is sent twice and old tasks are pruned automatically.
6. The bot switches between a slower "night mode" polling interval and a faster daytime interval based on the configured hours.

## Project structure

| File | Purpose |
|---|---|
| [`profi.py`](profi.py) | Main bot: scraping, filtering, and sending logic (`ProfiBotScraper`) |
| [`save_cookies.py`](save_cookies.py) | One-off script to log into Profi.ru and persist a session cookie file |
| [`clear_json.py`](clear_json.py) | Utility to deduplicate and clean up `state.json` |
| [`config_logging.py`](config_logging.py) | Logging configuration (console + rotating file log) |
| [`config.example.yaml`](config.example.yaml) | Template config — copy to `config.yaml` and fill in your own values |
| `requirements.txt` | Python dependencies |

## Setup

### 1. Install dependencies

```bash
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

Requires Google Chrome installed locally (`webdriver-manager` downloads a matching ChromeDriver automatically).

### 2. Configure

```bash
cp config.example.yaml config.yaml
```

Edit `config.yaml` with:

- Your Profi.ru login/password
- A Telegram bot token (create one via [@BotFather](https://t.me/BotFather))
- The Telegram chat/user/channel id that should receive notifications
- Your `good_words` / `bad_words` keyword filters
- Timing and browser settings

`config.yaml` is git-ignored — it holds your credentials and never gets committed.

### 3. Save a session

```bash
python3 save_cookies.py
```

This logs into Profi.ru once with Selenium and stores a cookie session file (`session`) so the main bot doesn't need to handle the login form on every run.

### 4. Run the bot

```bash
python3 profi.py
```

The bot runs two background threads: one searching for new tasks, one sending matched tasks to Telegram, and logs to both the console and `bot.log`.

## Configuration reference

| Key | Description |
|---|---|
| `auth.login` / `auth.password` | Your Profi.ru credentials |
| `auth.telegram_token` | Telegram bot token from BotFather |
| `auth.telegram_chat_id` | Destination chat/user/channel id |
| `search.good_words` | Keywords a task must contain to be forwarded |
| `search.bad_words` | Keywords that disqualify a task even if it matches a good word |
| `settings.refresh_interval` | Seconds between Telegram send cycles |
| `settings.batch_size` | Max tasks sent per cycle |
| `settings.scroll_pause_time` | Pause between feed scrolls, in seconds |
| `settings.night_start_hour` / `night_end_hour` | Hours during which polling slows down |
| `chrome.cookies_file` | Path to the saved session cookie file |
| `chrome.headless` | Run Chrome without a visible window |

## Disclaimer

This project automates interaction with Profi.ru through your own account and is intended for personal use. It is not affiliated with or endorsed by Profi.ru. Automating a third-party website may be against its terms of service — use at your own risk and discretion.

## License

[MIT](LICENSE)
