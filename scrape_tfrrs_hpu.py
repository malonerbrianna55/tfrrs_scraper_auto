"""
TFRRS scraper for High Point University track & field.

This scraper collects track & field performance data from TFRRS.org in two steps:
  1. Parse team roster pages to get a list of athletes and their profile URLs
  2. Visit each athlete's profile page to extract all their individual performances

ANTI-BLOCKING MEASURES:
TFRRS blocks automated scraping, so we use two strategies:
  1. User-agent rotation: Randomly select from 5+ different browser user agents
     to make requests look like they're coming from different devices/browsers
  2. Random delays: Wait 5-12 seconds between each request to avoid looking
     like a bot making rapid requests

"""

# library imports
import argparse  # For command-line argument parsing (--limit flag)
import re        # For regular expressions (pattern matching in text)
import time      # For adding delays between requests
import random    # For random user-agent selection and delay timing
import csv       # For writing CSV output file
from urllib.parse import urljoin  # For combining base URL with relative paths
import requests      # For making HTTP requests to fetch web pages
from bs4 import BeautifulSoup  # For parsing HTML and extracting data

##########################
# CONFIGURATION CONSTANTS
##########################

# Base URL for TFRRS used to convert relative URLs (athlete-specific) into full URLs
BASE = "https://www.tfrrs.org"

# Rotating through different user agents to make requests look like they're
# coming from different devices
USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.1 Safari/605.1.15",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:121.0) Gecko/20100101 Firefox/121.0",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 Mobile/15E148 Safari/604.1",
]

# URLs for HPU men's and women's track & field team pages.
# Starting points - we'll parse these pages to get athlete lists.
# swap for other teams later
HIGH_POINT_TEAM_URLS = [
    "https://www.tfrrs.org/teams/tf/NC_college_m_High_Point.html",  # Men's team
    "https://www.tfrrs.org/teams/tf/NC_college_f_High_Point.html",  # Women's team
]

# Randomizing wait time between requests so that it
# doesn't seem like a bot is making requests
DELAY_MIN = 3   # Minimum seconds to wait
DELAY_MAX = 7  # Maximum seconds to wait


##########################################################
# HELPER FUNCTIONS FOR NETWORK REQUESTS AND ANTI-BLOCKING
##########################################################

def get_session():
    """
    Function to create a requests session with a random user agent.
    
    Randomly selects a user agent from our list to make each
    request look like it's coming from a different device.
   
    """
    session = requests.Session()
    # Set headers that make the request look like a real browser
    session.headers.update({
        "User-Agent": random.choice(USER_AGENTS),  # Randomly pick a user agent
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",  # What content types we accept
        "Accept-Language": "en-US,en;q=0.5",  # Language preference
    })
    return session


def delay():
    """
    Function to wait a random amount of time between requests.
    The random timing makes it look more like human browsing behavior
    """
    time.sleep(random.uniform(DELAY_MIN, DELAY_MAX))


def fetch(session, url):
    """
    Function to fetch a web page and parse it into a BeautifulSoup object
    
    How it works:
    1. Makes an HTTP GET request to the URL
    2. Checks if the request was successful
    3. Parses the HTML into a BeautifulSoup object for data extraction
    4. Returns None if something goes wrong
    
    Arguments:
        session: requests.Session object
        url: The URL to fetch (string)
        
    Returns:
        BeautifulSoup object if successful, None if there was an error
    """
    try:
        # Make the HTTP request with a 30-second timeout
        r = session.get(url, timeout=30)
        # Raise an exception if the status code indicates an error
        r.raise_for_status()
        # Parse the HTML content into a BeautifulSoup object
        # 'html.parser' is the built-in parser
        return BeautifulSoup(r.text, "html.parser")
    except Exception as e:
        # If anything goes wrong (network error, it will print the error
        # and return None so the program can continue
        print(f"  Error fetching {url}: {e}")
        return None


##########################################################
# DATA CLEANING AND STANDARDIZATION FUNCTIONS
##########################################################

def normalize_class(year_text):
    """
    Function to convert class year text to standardized format.
    
    TFRRS displays class years in various formats like "FR-1", "SO-2", "JR-3",
    "SR-4", "RS/Una", etc. This function standardizes them to just "FR", "SO",
    "JR", "SR", or "RS" for consistency in our output.
    
    Arguments:
        year_text: Raw class text from the roster (e.g., "FR-1", "SO-2")
        
    Returns:
        str: Normalized class code ("FR", "SO", "JR", "SR", or "RS")
    """
    if not year_text:
        return ""
    # Convert to uppercase and remove whitespace for consistent matching
    year_text = year_text.strip().upper()
    
    # Check for each class type in order
    if year_text.startswith("FR"):
        return "FR"  # Freshman
    if year_text.startswith("SO"):
        return "SO"  # Sophomore
    if year_text.startswith("JR"):
        return "JR"  # Junior
    if year_text.startswith("SR"):
        return "SR"  # Senior
    if "RS" in year_text or "UNA" in year_text:
        return "RS"  # Redshirt or Unattached
    
    # Backup method: try to extract first two uppercase letters (e.g., "FR" from "FR-1")
    m = re.match(r"([A-Z]{2})", year_text)
    return m.group(1) if m else year_text


def extract_year_from_date(date_str):
    """
    Extract the 4-digit year from a date string.
    
    Date strings on TFRRS can be messy (e.g., "Feb 6- 7, 2026" or
    "December 4- 5, 2025"). This function finds and extracts just the year.
    
    Args:
        date_str: Date string that may contain a year
        
    Returns:
        str: 4-digit year (e.g., "2026") or empty string if not found
    """
    if not date_str:
        return ""
    # Look for a 4-digit number starting with 19 or 20 (years 1900-2099)
    # \b means word boundary (ensures we match whole years, not parts of other numbers)
    m = re.search(r"\b(19|20)\d{2}\b", date_str)
    return m.group(0) if m else ""


def clean_date_cell(date_str):
    """
    Function to extract a clean date string from a cell that may contain extra text.
    
    Date cells on TFRRS contain meet names
    This function extracts just the date portion
    
    Arguments:
        date_str: Raw date cell text
        
    Returns:
        str: Clean date string (e.g., "Feb 7, 2026")
    """
    if not date_str:
        return ""
    
    # Explaination:
    # [A-Za-z]+ - Month name (one or more letters)
    # \s+ - One or more spaces
    # \d{1,2} - Day (1-2 digits)
    # (?:\s*-\s*\d{1,2})? - Optional: dash and second day (for date ranges)
    # ,? - Optional comma
    # \s+ - Spaces
    # (?:20)\d{2} - 4-digit year starting with 20
    m = re.search(
        r"([A-Za-z]+\s+\d{1,2}(?:\s*-\s*\d{1,2})?,?\s+(?:20)\d{2})",
        date_str.strip(),
    )
    # Return match if found
    # Otherwise return first 50 chars as fallback to avoid errors
    return m.group(1).strip() if m else date_str.strip()[:50]


##########################################################
# PARSING FUNCTIONS - STEP 1: ROSTER PARSING
##########################################################

def parse_roster(soup, team_url, gender):
    """
    Function to parse the team roster page and extract athlete information.
    
    STEP 1 of the scraping process.
    
    Arguments:
        soup: BeautifulSoup object containing the parsed HTML of the roster page
        team_url: URL of the team page (used to determine gender)
        gender: 'M' or 'F' (determined from team URL - "_m_" vs "_f_")
        
    Returns:
        list: List of dictionaries, each containing:
            - name: Athlete's name
            - url: Full URL to athlete's profile page
            - class: Normalized class (FR/SO/JR/SR/RS)
            - gender: M or F
    """
    athletes = []
    
    # Finding the ROSTER section by looking for heading tags (h3 or h4) that contain "ROSTER"
    for h in soup.find_all(["h3", "h4"]):
        heading_text = (h.get_text() or "").upper()
        if "ROSTER" not in heading_text:
            continue  # Skip headings that aren't the roster section
        
        # Finding the table that comes after this heading
        table = h.find_next("table")
        if not table:
            continue  # Skip if no table found
        
        # Getting all rows (tr) in the table
        rows = table.find_all("tr")
        
        # Processing each row (skip the first one, which is usually the header)
        for tr in rows[1:]:
            # Getting all cells (td) in this row
            cells = tr.find_all("td")
            if len(cells) < 2:
                continue  # Skip rows that don't have at least 2 columns
            
            # First cell should contain a link to the athlete's profile
            # Look for an <a> tag with href containing "/athletes/"
            a = cells[0].find("a", href=re.compile(r"/athletes/"))
            if not a:
                continue  # Skip if no athlete link found
            
            # Extract the athlete's name from the link text
            name = (a.get_text() or "").strip()
            
            # Get the href relative link "/athletes/123/..."
            href = a.get("href") or ""
            
            # Convert relative URLs to absolute URLs
            # If href starts with "/", it's relative, so join with BASE URL
            # Otherwise, assume it's already absolute
            url = urljoin(BASE, href) if href.startswith("/") else href
            
            # Second cell contains the class year (SR, JR, SO, FR, RS)
            year_cell = cells[1].get_text().strip() if len(cells) > 1 else ""
            
            # Add this athlete to our list
            athletes.append({
                "name": name,
                "url": url,
                "class": normalize_class(year_cell),  # Normalize to FR/SO/JR/SR/RS
                "gender": gender,
            })
        
        # Once we've found and processed the roster table, we're done
        # (there should only be one roster table per page)
        break
    
    return athletes


# #############################
# TRANSFER DETECTION FUNCTION
###############################

def is_transfer(soup):
    """
    Determine if an athlete is a transfer student.
    
    TFRRS indicates transfers on athlete profile pages with text like:
    - "previously at [School Name]"
    - "Prior: [School Name]"
    
    This function searches the entire page text for these indicators.
    
    Args:
        soup: BeautifulSoup object containing the athlete's profile page HTML
        
    Returns:
        bool: True if transfer indicators are found, False otherwise
    """
    # Get all text from the page 
    # removes HTML tags, just leaves text content
    text = soup.get_text() if soup else ""
    text_lower = text.lower()  # Convert to lowercase for case-insensitive matching
    
    # Check for common transfer indicators
    if "previously at" in text_lower or "prior:" in text_lower or "transferred" in text_lower:
        return True
    
    # Some pages use variations like "Prior school" or "* previously"
    if "prior" in text_lower and "school" in text_lower:
        return True
    
    return False


##########################################################
# PARSING FUNCTIONS - STEP 2: ATHLETE PERFORMANCE PARSING
##########################################################

def parse_athlete_performances(soup, athlete_info):
    """
    Parse an athlete's profile page to extract all their performances.
    
    This is STEP 2 of the scraping process. Each athlete profile page contains
    multiple tables with performance data. The structure is:
    
    Meet Results Table Structure:
        <table>
            <tr>
                <td>Meet Name</td>
                <td>Feb 6- 7, 2026</td>  <!-- Date row (header for this meet) -->
            </tr>
            <tr>
                <td>200</td>              <!-- Event name -->
                <td><a href="...">21.85</a></td>  <!-- Mark (performance) -->
                <td>6th (F)</td>          <!-- Place -->
            </tr>
            <tr>
                <td>400</td>
                <td><a href="...">47.63</a></td>
                <td>1st (F)</td>
            </tr>
            <!-- Next meet starts with another date row... -->
        </table>
    
    The challenge: We need to:
    1. Identify rows that contain dates (these mark the start of a new meet)
    2. Track the current date as we process rows
    3. Extract event names and marks from performance rows
    4. Skip rows from other tables (like "College Bests" which has different structure)
    
    Args:
        soup: BeautifulSoup object containing the athlete's profile page HTML
        athlete_info: Dictionary with name, class, gender from roster parsing
        
    Returns:
        list: List of dictionaries, each representing one performance:
            - name: Athlete's name
            - event: Event name (e.g., "200", "Mile", "High Jump")
            - mark: Performance result (e.g., "21.85", "4:13.15", "2.08m")
            - performance_date: Clean date string (e.g., "Feb 7, 2026")
            - year: Extracted year (e.g., "2026")
            - class: Academic class (FR/SO/JR/SR/RS)
            - gender: M or F
            - transfer: Yes or No
            - school: School name where athlete was competing (e.g., "HIGH POINT")
    """
    # Start with athlete info from the roster
    name = athlete_info.get("name", "")
    class_ = athlete_info.get("class", "")
    gender = athlete_info.get("gender", "")
    
    # Check if this athlete is a transfer
    transfer = "Yes" if is_transfer(soup) else "No"

    # Try to get name and class from the page header
    for h in soup.find_all(["h3", "h4"]):
        raw = (h.get_text() or "").strip()
        # Look for pattern like "NAME (CLASS)"
        if raw and "(" in raw and ")" in raw:
            # Match example: "TIM BROWN (SO-2)" -> name="TIM BROWN", class="SO"
            name_match = re.match(r"^(.+?)\s*\(([A-Z]{2})", raw)
            if name_match:
                name = name_match.group(1).strip()
                # Only override class if we don't already have one from roster
                if not class_:
                    class_ = name_match.group(2)
            break

    # Extract school name from page header (e.g., "HIGH POINT")
    # The school name is typically shown in an h3 or h4 tag near the top
    school_name = ""
    for h in soup.find_all(["h3", "h4"]):
        header_text = (h.get_text() or "").strip().upper()
        # Skip if it's the athlete name header (contains parentheses with class)
        if "(" in header_text and ")" in header_text:
            continue
        # Look for school name - it's usually a short name like "HIGH POINT"
        # and appears after the athlete name header
        if header_text and len(header_text) < 50 and header_text != name.upper():
            school_name = header_text
            break

    # For transfer athletes, TFRRS inserts a <div class="col-lg-12 transfer"> marker
    # between the current-school meet results and the prior-school meet results
    # We will walk through in order and flag when we pass the transfer marker,
    # so each table gets the right school.

    # Find the transfer marker div (class includes "transfer")
    transfer_marker = soup.find("div", class_="transfer")
    competing_for_school = None
    if transfer_marker:
        link = transfer_marker.find("a", href=re.compile(r"/teams/"))
        if link:
            competing_for_school = (link.get_text() or "").strip() or None

    # Build a set of table IDs that belong to the prior school by walking through "siblings"
    prior_school_table_ids = set()
    if transfer_marker and competing_for_school:
        parent = transfer_marker.parent
        past_marker = False
        for sib in parent.children:
            if not hasattr(sib, "name") or not sib.name:
                continue
            if sib is transfer_marker:
                past_marker = True
                continue
            if past_marker:
                # Every table inside this sibling div belongs to the prior school
                for tbl in sib.find_all("table"):
                    prior_school_table_ids.add(id(tbl))

    def school_for_table(tbl):
        """Return the school for this table."""
        if id(tbl) in prior_school_table_ids:
            return competing_for_school
        return school_name

    # List to store all performance records we extract
    rows = []

    # Each meet on TFRRS is its own <table>. The structure is:
    #   <table>
    #     <thead><tr><th>  [Meet Name link]  [Date span]  </th></tr></thead>
    #     <tr><td>Event</td><td><a href="/results/...">Mark</a></td><td>Place</td></tr>
    #     ...
    #   </table>
    # So we read the date from <thead> and performances from the <tbody> <tr> rows.

    for table in soup.find_all("table"):
        # For transfer athletes, this table may be under "Competing for [Prior School]"
        table_school = school_for_table(table)

        # Extract date from <thead>
        thead = table.find("thead")
        if not thead:
            continue  # Skip tables with no header (not a meet results table)

        thead_text = (thead.get_text() or "").strip()
        current_date_str = clean_date_cell(thead_text)
        current_year = extract_year_from_date(current_date_str)

        # If we couldn't find a valid year in the header, skip this table
        if not current_year:
            continue

        # Convert calendar year to academic year.
        # The college season spans two calendar years (ex. 2025-26 runs Aug 2025
        # through Jun 2026). Meets in Aug-Dec belong to the academic year that
        # ends the following spring, so bump those up by 1.
        # for example, Dec 2025 is academic year 2026, Feb 2026 is academic year 2026.
        fall_months = ("aug", "sep", "oct", "nov", "dec")
        date_lower = current_date_str.lower()
        if any(date_lower.startswith(m) for m in fall_months):
            current_acad_year = str(int(current_year) + 1)
        else:
            current_acad_year = current_year

        # Extract performance rows from table body
        for tr in table.find_all("tr"):
            # Skip header rows (they live in <thead>, which we already handled)
            if tr.find_parent("thead"):
                continue

            tds = tr.find_all("td")

            # Need at least 2 cells- event and mark
            if len(tds) < 2:
                continue

            # First cell = event name
            event_cell = (tds[0].get_text() or "").strip()

            # Skip empty or header-like cells
            if event_cell.upper() in ("EVENT", "MEET", ""):
                continue

            # Skip rows where the first cell looks like a mark/time, not an event name
            # (these come from "College Bests" or "Event History" tables)
            # Marks contain a decimal or colon, event names that are integers
            if re.match(r"^\d+\.\d+$", event_cell) or re.match(r"^\d+:\d+", event_cell) or re.match(r"^\d+\.?\d*m$", event_cell):
                continue

            # Second cell = mark (usually inside a /results/ link)
            link = tr.find("a", href=re.compile(r"/results/"))
            if link:
                mark = (link.get_text() or "").strip()
            else:
                mark = (tds[1].get_text() or "").strip()

            # Skip missing or implausibly long marks
            if not mark or len(mark) > 25:
                continue

            rows.append({
                "name": name,
                "event": event_cell,
                "mark": mark,
                "performance_date": current_date_str,
                "year": current_year,
                "acad_year": current_acad_year,
                "current_class": class_,
                "gender": gender,
                "transfer": transfer,
                "school": table_school,
            })

    ########################################################################
    # Calculate class_at_mark for each row.
    # Start from the first academic year the athlete competed (FR) and count
    # forward SO, JR, SR. Beyond 4 years label as SR-5, SR-6, etc.
    # Gaps (redshirt/missing years) are skipped automatically since we only
    # have entries for years the athlete actually competed.
    ########################################################################
    if rows:
        all_acad_years = sorted({int(r["acad_year"]) for r in rows if r["acad_year"]})
        CLASS_FORWARD = ["FR", "SO", "JR", "SR"]
        year_to_class = {}
        for i, year in enumerate(all_acad_years):
            if i < len(CLASS_FORWARD):
                year_to_class[year] = CLASS_FORWARD[i]
            else:
                year_to_class[year] = f"SR-{i + 1}"
        for row in rows:
            row["class_at_mark"] = year_to_class.get(int(row["acad_year"]), "") if row["acad_year"] else ""
    else:
        for row in rows:
            row["class_at_mark"] = ""

    return rows


###########################
# REUSABLE SCRAPE FUNCTION
###########################

def scrape_teams(team_urls, session=None, limit=0, output_path="tfrrs_performances.csv"):
    # Scrape roster and performances for a list of team URLs.


    if session is None:
        session = get_session()
    all_rows = []
    for team_url in team_urls:
        gender = "M" if "_m_" in team_url else "F"
        print(f"Fetching roster: {team_url}")
        delay()
        soup = fetch(session, team_url)
        if not soup:
            print(f"  Failed to fetch roster, skipping...")
            continue
        athletes = parse_roster(soup, team_url, gender)
        if limit:
            athletes = athletes[:limit]
        print(f"  Processing {len(athletes)} athletes.")
        for i, ath in enumerate(athletes):
            print(f"  [{i+1}/{len(athletes)}] {ath['name']}")
            delay()
            a_soup = fetch(session, ath["url"])
            if not a_soup:
                print(f"    Failed to fetch profile, skipping...")
                continue
            perfs = parse_athlete_performances(a_soup, ath)
            all_rows.extend(perfs)
            print(f"    Found {len(perfs)} performances")
    fieldnames = ["name", "event", "mark", "performance_date", "year", "acad_year", "current_class", "class_at_mark", "gender", "transfer", "school"]
    with open(output_path, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames)
        w.writeheader()
        w.writerows(all_rows)
    print(f"\nWrote {len(all_rows)} rows to {output_path}.")
    return all_rows


###########################
# MAIN EXECUTION FUNCTION
###########################

def main():
    """
    Main function that combines all the functions above to scrape the data
    
    Process flow:
    1. Parse command-line arguments (use --limit for testing)
    2. Create a session with random user agent
    3. For each team (men's and women's):
       a. Fetch the roster page
       b. Parse athlete list from roster
       c. For each athlete:
          - Fetch their profile page
          - Parse all performances
          - Add performances to list
    4. Write all collected data to CSV file
   
    """
    
    # #############################################
    # SETUP - Parse command-line arguments
    # #############################################
    
    parser = argparse.ArgumentParser(description="Scrape TFRRS for High Point University.")
    # --limit flag allows testing with just a few athletes instead of scraping all
    parser.add_argument("--limit", type=int, default=0, 
                       help="Max athletes per team (0 = all). Use 2-3 to test.")
    args = parser.parse_args()

    session = get_session()
    scrape_teams(
        HIGH_POINT_TEAM_URLS,
        session=session,
        limit=args.limit,
        output_path="high_point_tfrrs_performances.csv",
    )


# ###############
# MAIN FUNCTION
# ###############

if __name__ == "__main__":
    # This allows the script to be run from command line: python scrape_tfrrs.py
    main()
