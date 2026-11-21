import json
import os
import re
import time

from datetime import datetime, timezone
from html.parser import HTMLParser
from urllib.request import Request, urlopen
from urllib.parse import urljoin, urlparse
from urllib.error import URLError, HTTPError


BASE = "https://21.mchs.gov.ru"
SOURCE = BASE + "/deyatelnost/press-centr/vse_novosti"
OUTPUT = "data/alerts.json"


class Parser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.links = set()
        self.h1 = ""
        self.text = ""
        self.in_h1 = False
        self.published = ""

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)

        if tag == "a":
            url = urljoin(BASE, attrs.get("href", ""))
            parsed = urlparse(url)

            if (
                parsed.netloc == "21.mchs.gov.ru"
                and "/deyatelnost/press-centr/" in parsed.path
                and parsed.path.rstrip("/") !=
                "/deyatelnost/press-centr/vse_novosti"
            ):
                self.links.add(url)

        if tag == "h1":
            self.in_h1 = True

        if tag == "time":
            self.published = attrs.get("datetime", "")

        if tag == "meta" and attrs.get("property") == "article:published_time":
            self.published = attrs.get("content", "")

    def handle_data(self, data):
        self.text += " " + data

        if self.in_h1:
            self.h1 += " " + data

    def handle_endtag(self, tag):
        if tag == "h1":
            self.in_h1 = False


def fetch(url):
    last_error = None

    for attempt in range(3):
        try:
            request = Request(
                url,
                headers={
                    "User-Agent": "Mozilla/5.0 FlyRadar/1.0"
                }
            )

            with urlopen(request, timeout=60) as response:
                if response.status != 200:
                    raise RuntimeError(
                        f"HTTP status: {response.status}"
                    )

                return response.read().decode(
                    "utf-8", errors="replace"
                )

        except (URLError, TimeoutError, HTTPError) as error:
            last_error = error
            print(f"Attempt {attempt + 1} failed: {error}")

            if attempt < 2:
                time.sleep(10 * (attempt + 1))

    raise RuntimeError(
        f"Official source unavailable after 3 attempts: {last_error}"
    )


def classify(title, body):
    title = title.lower()
    body = body.lower()
    combined = title + " " + body[:3000]

    if "чуваш" not in combined:
        return None

    rocket = bool(re.search(r"ракетн\w*\s+опасность", combined))

    drone = bool(re.search(
        r"беспилотн\w*\s+опасность|опасность\w*\s+атак\w*\s+бпла",
        combined
    ))

    cancelled = bool(re.search(r"отбой|отмен\w*", title))

    if rocket and cancelled:
        return "rocket_cancelled"

    if drone and cancelled:
        return "drone_cancelled"

    if rocket and re.search(r"объявлен\w*|введен\w*", combined):
        return "rocket_warning"

    if drone and re.search(r"объявлен\w*|введен\w*", combined):
        return "drone_warning"

    return None


def main():
    print("FlyRadar: starting collection")

    listing = Parser()
    listing.feed(fetch(SOURCE))

    results = []

    for url in sorted(listing.links):
        try:
            page = Parser()
            page.feed(fetch(url))

            title = re.sub(r"\s+", " ", page.h1).strip()

            if not title:
                continue

            event = classify(title, page.text)

            if event is None:
                continue

            results.append({
                "title": title,
                "type": event,
                "url": url,
                "publishedAt": page.published or None,
                "source": "МЧС России по Чувашской Республике"
            })

        except Exception as error:
            print("Page skipped:", url, error)

    results.sort(
        key=lambda item: item["publishedAt"] or "",
        reverse=True
    )

    os.makedirs("data", exist_ok=True)

    output = {
        "region": "Чувашская Республика",
        "collectedAt": datetime.now(timezone.utc).isoformat(),
        "source": SOURCE,
        "items": results[:50]
    }

    with open(OUTPUT, "w", encoding="utf-8") as file:
        json.dump(output, file, ensure_ascii=False, indent=2)

    print("Matching publications:", len(results))
    print("FlyRadar: collection finished")


if __name__ == "__main__":
    main()
