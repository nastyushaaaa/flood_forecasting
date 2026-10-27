from datetime import datetime
from typing import Any

from playwright.sync_api import sync_playwright


class _PageNotFound(Exception):
    """Internal marker: page returned 4xx/5xx (wrong river/city slug)."""


def get_chart_data(river: str, city: str, timeout_ms: int = 60_000, chart_timeout_ms: int = 15_000) -> dict | list | None:
    url = f"https://allrivers.info/gauge/{river}-{city}/waterlevel/"

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(
            user_agent=(
                "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
                "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
            ),
            locale="ru-RU",
        )
        page = context.new_page()

        try:
            try:
                with page.expect_response(
                    lambda r: "/chart" in r.url
                    and r.request.resource_type in ("xhr", "fetch"),
                    timeout=chart_timeout_ms,
                ) as response_info:
                    response = page.goto(url, wait_until="domcontentloaded", timeout=timeout_ms)
                    if response is None or response.status >= 400:
                        raise _PageNotFound()
            except:
                return None

            return response_info.value.json()
        finally:
            context.close()
            browser.close()


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
    data = get_chart_data(river, city)
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
