"""
TFRRS scraper for Big South Conference track & field

Uses scrape_tfrrs_hpu for all roster and performance scraping. This file:
  1. Fetches the Big South conference league page
  2. Parses the TEAMS table to get every men's and women's team URL
  3. Calls scrape_tfrrs_hpu.scrape_teams() to scrape each team (rosters + athlete performances)

Anti-blocking (delays, user-agent rotation) and CSV output are handled by scrape_tfrrs_hpu
"""

# Import libraries
import argparse
from urllib.parse import urlparse

from bs4 import BeautifulSoup

# Reuse HPU scraper for roster + athlete performance scraping
import scrape_tfrrs_hpu

# Big South conference league page
BIG_SOUTH_LEAGUE_URL = "https://tfrrs.org/leagues/64.html"
CONFERENCE_NAME = "Big South"
BASE = "https://www.tfrrs.org"


def _normalize_team_url(href):

    # Convert a relative team link to a full URL using BASE.

    # Keeps URLs consistent with TFRRS so they match what
    #scrape_tfrrs_hpu expects when fetching roster pages.

    href = (href or "").strip()
    if not href:
        return None
    # If already absolute, keep only the path
    if href.startswith("http"):
        parsed = urlparse(href)
        path = parsed.path or ""
        return BASE + path
    # If relative, add BASE and leading slash if missing
    return BASE + (href if href.startswith("/") else "/" + href)


def extract_teams_from_conference_page(soup, conference_name):
    """
    Parse a TFRRS league/conference page and extract the team roster.

    Arguments:
        soup: BeautifulSoup object of the league page (from fetch()).
        conference_name: ex. "Big South"

    Returns:
        List of (school_name, gender, team_url)
    """
    teams = []
    # Find the section that contains the teams table (heading text contains "TEAMS")
    for heading in soup.find_all(["h1", "h2", "h3", "h4", "h5", "h6"]):
        if "TEAMS" not in (heading.get_text() or "").upper():
            continue
        table = heading.find_next("table")
        if not table:
            continue
        rows = table.find_all("tr")
        # Skip first row with gender headers
        for row in rows[1:]:
            cells = row.find_all("td")
            if len(cells) < 2:
                continue
            # Column 0 = men's team, column 1 = women's team
            for col_index, gender in enumerate(("M", "F")):
                link = cells[col_index].find("a", href=True)
                # Only accept links that point to a team page
                if not link or "/teams/tf/" not in (link.get("href") or ""):
                    continue
                url = _normalize_team_url(link["href"])
                if url:
                    name = (link.get_text() or "").strip()
                    teams.append((name, gender, url))
        break
    return teams


def main():
    # Run the Big South scrape: fetch conference page, parse team list, scrape
    # each team (rosters and performances) via scrape_tfrrs_hpu.

    # --limit for testing with fewer athletes per team
    parser = argparse.ArgumentParser(description="Scrape TFRRS for Big South Conference.")
    parser.add_argument("--limit", type=int, default=0, help="Max athletes per team (0 = all). Use 2-3 to test.")
    args = parser.parse_args()

    # Reuse the same session and anti-blocking behavior as the HPU scraper
    session = scrape_tfrrs_hpu.get_session()
    scrape_tfrrs_hpu.delay()

    # Step 1: Fetch the conference league page
    print(f"Fetching conference page: {BIG_SOUTH_LEAGUE_URL}")
    soup = scrape_tfrrs_hpu.fetch(session, BIG_SOUTH_LEAGUE_URL)
    if not soup:
        print("Failed to fetch conference page. Exiting.")
        return

    # Step 2: Parse the page to get all team URLs
    teams = extract_teams_from_conference_page(soup, CONFERENCE_NAME)
    team_urls = [url for (_name, _gender, url) in teams]
    print(f"Found {len(team_urls)} teams. Scraping via scrape_tfrrs_hpu...\n")

    # Step 3: Use team scraping function
    # from HPU scraper to fetch each team's roster and athlete performances
    scrape_tfrrs_hpu.scrape_teams(
        team_urls,
        session=session,
        limit=args.limit,
        output_path="big_south_tfrrs_performances.csv",
    )


if __name__ == "__main__":
    main()

# Total run time: ~ 51 minutes, 22 seconds