from datetime import datetime
from typing import Any
import json
import logging
import time
import csv

from playwright.sync_api import sync_playwright, Error as PlaywrightError


logger = logging.getLogger(__name__)


class _PageNotFound(Exception):
    """Internal marker: page returned 4xx/5xx (wrong river/city slug)."""

def get_chart_data(
    url: str,
    timeout_ms: int = 60_000,
    chart_timeout_ms: int = 15_000,
    max_retries: int = 3,
    base_delay: float = 2.0,
) -> dict | None:
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        try:
            for attempt in range(max_retries):
                # If the browser itself crashed (Target closed / Browser closed),
                # reusing it would make retries fail instantly. Relaunch.
                if not browser.is_connected():
                    logger.warning("Browser disconnected, relaunching for %s", url)
                    browser = p.chromium.launch(headless=True)

                try:
                    return _fetch_chart_response(browser, url, timeout_ms, chart_timeout_ms)
                except _PageNotFound:
                    logger.warning("Page not found (4xx/5xx): %s", url)
                    raise
                except PlaywrightError as exc:
                    if attempt == max_retries - 1:
                        logger.error(
                            "Playwright error after %d attempts for %s: %s",
                            max_retries, url, exc,
                        )
                        return None
                    delay = base_delay * (2 ** attempt)
                    logger.info(
                        "Playwright error, retry %d/%d in %.1fs for %s: %s",
                        attempt + 1, max_retries, delay, url, exc,
                    )
                    time.sleep(delay)
                except json.JSONDecodeError as exc:
                    logger.error("Invalid JSON from %s: %s", url, exc)
                    return None
        finally:
            browser.close()
    return None


def _fetch_chart_response(
    browser,
    url: str,
    timeout_ms: int,
    chart_timeout_ms: int,
) -> dict:
    """One attempt: fresh context+page on a reused browser."""
    context = browser.new_context(
        user_agent=(
            "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
            "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
        ),
        locale="ru-RU",
    )
    try:
        page = context.new_page()
        with page.expect_response(
            lambda r: "/chart" in r.url
            and r.request.resource_type in ("xhr", "fetch"),
            timeout=chart_timeout_ms,
        ) as response_info:
            response = page.goto(url, wait_until="domcontentloaded", timeout=timeout_ms)
            if response is None or response.status >= 400:
                raise _PageNotFound(url)
        return response_info.value.json()
    finally:
        context.close()

def _to_number(v: Any) -> float | int | None:
    """Coerce a JSON value to int/float, or None if it isn't numeric."""
    if isinstance(v, bool) or v is None:
        return None
    if isinstance(v, (int, float)):
        return v
    try:
        return int(v)
    except (TypeError, ValueError):
        try:
            return float(v)
        except (TypeError, ValueError):
            return None


def get_water_levels(river: str, city: str) -> dict[datetime, float]:
    try:
        data = get_chart_data(f"https://allrivers.info/gauge/{river}-{city}/waterlevel/")
    except _PageNotFound:
        logger.warning("Station not found: %s-%s", river, city)
        return {}
    if data is None:
        return {}

    graph = data.get("graphdata") if isinstance(data, dict) else None
    if not isinstance(graph, dict):
        return {}

    series: dict[datetime, float] = {}

    for year_key, points in graph.items():
        try:
            year_int = int(year_key)
        except (TypeError, ValueError):
            continue
        if not isinstance(points, list):
            continue

        for item in points:
            try:
                ts_ms, raw_value = item
            except (TypeError, ValueError):
                continue

            value = _to_number(raw_value)
            if value is None:
                continue

            try:
                ts = datetime.fromtimestamp(ts_ms / 1000)
            except (OverflowError, OSError, ValueError):
                continue

            try:
                dt = ts.replace(year=year_int)
            except ValueError:
                # Feb 29 when the target year isn't a leap year
                continue

            series[dt] = value

    return dict(sorted(series.items()))


def update_water_levels(inter_request_delay: float = 0.0) -> None:
    """Fetch water levels for every station from tracked_stations.csv.

    inter_request_delay: seconds to sleep between stations (0 = no delay).
    The old hardcoded 15 s sleep in get_chart_data has been removed — if the
    upstream site requires rate-limiting, set this explicitly.
    """
    with open("tracked_stations.csv", newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        first = True
        for row in reader:
            if not first and inter_request_delay > 0:
                time.sleep(inter_request_delay)
            first = False
            try:
                river_name = row["river"]
                station_name = row["station"]
            except (KeyError, TypeError, ValueError):
                continue
            get_water_levels(river_name, station_name)