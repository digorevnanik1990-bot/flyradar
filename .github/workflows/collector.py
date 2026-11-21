import json
import os
import re
from datetime import datetime, timezone
from html.parser import HTMLParser
from urllib.request import Request, urlopen
from urllib.parse import urljoin, urlparse

BASE = "https://21.mchs.gov.ru"
SOURCE = BASE + "/deyatelnost/press-centr/vse_novosti"
OUTPUT = "data/alerts.json"


class Parser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.links = set()
        self.title = ""
        self.h1 = ""
        self.text = ""
        self.in_h1 = False
        self.published = ""

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)

        if tag == "a":
            href = attrs.get("href", "")
            url = urljoin(BASE, href)
            path = urlparse(url).path

            if (
                urlparse(url).netloc == "21.mchs.gov.ru"
                and "/deyatelnost/press-centr/" in path
                and path.rstrip("/") !=
                "/deyatelnost/press-centr/vse_novosti"
            ):
                self.links.add(url)

        if tag == "h1":
            self.in_h1 = True

        if tag == "time":
            self.published = attrs.get("datetime", "")

        if tag == "meta":
            if attrs.get("property") == "article:published_time":
                self.published = attrs.get("content", "")

    def handle_data(self, data):
        self.text += " " + data
        if self.in_h1:
            self.h1 += " " + data

    def handle_endtag(self, tag):
        if tag == "h1":
            self.in_h1 = False


def fetch(url):
    request = Request(
        url,
        headers={"User-Agent": "FlyRadar/1.0"}
    )
    with urlopen(request, timeout=25) as response:
        if response.status != 200:
            raise RuntimeError("Source unavailable")
        return response.read().decode("utf-8", errors="replace")


def classify(title, text):
    title = title.lower()
    beginning = text[:1800].lower()

    region = (
        "чуваш" in title or
        "чуваш" in beginning
    )

    if not region:
        return None

    combined = title + " " + beginning

    rocket = bool(re.search(r"ракетн\w*\s+опасност", combined))
    drone = bool(re.search(
        r"(беспилотн\w*\s+опасност|опасност\w*\s+атак\w*\s+бпла)",
        combined
    ))

    cancellation = bool(re.search(
        r"(отбой|отмен\w*)",
        title
    ))

    if rocket and cancellation:
        return "rocket_cancelled"

    if drone and cancellation:
        return "drone_cancelled"

    if rocket and re.search(r"объявлен\w*|введен\w*", combined):
        return "rocket_warning"

    if drone and re.search(r"объявлен\w*|введен\w*", combined):
        return "drone_warning"

    return None


def main():
    listing = Parser()
    listing.feed(fetch(SOURCE))

    results = []

    for url in sorted(listing.links):
        if not re.search(r"/(novosti|operativnaya-informaciya)/", url):
            continue

        try:
            page = Parser()
            page.feed(fetch(url))

            title = re.sub(r"\s+", " ", page.h1).strip()
            if not title:
                continue

            event = classify(title, page.text)
            if not event:
                continue

            results.append({
                "title": title,
                "type": event,
                "url": url,
                "publishedAt": page.published or None,
                "source": "МЧС России по Чувашской Республике"
            })

        except Exception as error:
            print("Page skipped:", url, str(error))

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

    print("Matching official publications:", len(results))


if __name__ == "__main__":
    main()
