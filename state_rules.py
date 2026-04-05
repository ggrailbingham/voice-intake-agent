"""
state_rules.py
--------------
State rules lookup tool. Called mid-conversation when the customer
provides their state. Returns age requirements only.
"""

import json
import os
import re

RULES_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "state_rules.json")

NAME_TO_ABBR = {
    "ALABAMA": "AL", "ALASKA": "AK", "ARIZONA": "AZ", "ARKANSAS": "AR",
    "CALIFORNIA": "CA", "COLORADO": "CO", "CONNECTICUT": "CT", "DELAWARE": "DE",
    "FLORIDA": "FL", "GEORGIA": "GA", "HAWAII": "HI", "IDAHO": "ID",
    "ILLINOIS": "IL", "INDIANA": "IN", "IOWA": "IA", "KANSAS": "KS",
    "KENTUCKY": "KY", "LOUISIANA": "LA", "MAINE": "ME", "MARYLAND": "MD",
    "MASSACHUSETTS": "MA", "MICHIGAN": "MI", "MINNESOTA": "MN", "MISSISSIPPI": "MS",
    "MISSOURI": "MO", "MONTANA": "MT", "NEBRASKA": "NE", "NEVADA": "NV",
    "NEW HAMPSHIRE": "NH", "NEW JERSEY": "NJ", "NEW MEXICO": "NM", "NEW YORK": "NY",
    "NORTH CAROLINA": "NC", "NORTH DAKOTA": "ND", "OHIO": "OH", "OKLAHOMA": "OK",
    "OREGON": "OR", "PENNSYLVANIA": "PA", "RHODE ISLAND": "RI", "SOUTH CAROLINA": "SC",
    "SOUTH DAKOTA": "SD", "TENNESSEE": "TN", "TEXAS": "TX", "UTAH": "UT",
    "VERMONT": "VT", "VIRGINIA": "VA", "WASHINGTON": "WA", "WEST VIRGINIA": "WV",
    "WISCONSIN": "WI", "WYOMING": "WY"
}

# Common US cities mapped to their state abbreviation.
# Used so "I live in Fresno" correctly resolves to CA
# without relying on abbreviation matching.
CITY_TO_STATE = {
    # California
    "LOS ANGELES": "CA", "LA": "CA", "SAN FRANCISCO": "CA", "SF": "CA",
    "SAN DIEGO": "CA", "SAN JOSE": "CA", "FRESNO": "CA", "SACRAMENTO": "CA",
    "LONG BEACH": "CA", "OAKLAND": "CA", "BAKERSFIELD": "CA", "ANAHEIM": "CA",
    "SANTA ANA": "CA", "RIVERSIDE": "CA", "STOCKTON": "CA", "IRVINE": "CA",
    # New York
    "NEW YORK CITY": "NY", "NYC": "NY", "NEW YORK": "NY", "BUFFALO": "NY",
    "ROCHESTER": "NY", "YONKERS": "NY", "BROOKLYN": "NY", "MANHATTAN": "NY",
    "QUEENS": "NY", "BRONX": "NY", "STATEN ISLAND": "NY",
    # Texas
    "HOUSTON": "TX", "SAN ANTONIO": "TX", "DALLAS": "TX", "AUSTIN": "TX",
    "FORT WORTH": "TX", "EL PASO": "TX", "ARLINGTON": "TX", "CORPUS CHRISTI": "TX",
    # Florida
    "JACKSONVILLE": "FL", "MIAMI": "FL", "TAMPA": "FL", "ORLANDO": "FL",
    "ST PETERSBURG": "FL", "HIALEAH": "FL", "TALLAHASSEE": "FL",
    # Illinois
    "CHICAGO": "IL", "AURORA": "IL", "JOLIET": "IL", "ROCKFORD": "IL",
    # Pennsylvania
    "PHILADELPHIA": "PA", "PITTSBURGH": "PA", "ALLENTOWN": "PA",
    # Ohio
    "COLUMBUS": "OH", "CLEVELAND": "OH", "CINCINNATI": "OH", "TOLEDO": "OH",
    # Georgia
    "ATLANTA": "GA", "AUGUSTA": "GA", "COLUMBUS GA": "GA", "SAVANNAH": "GA",
    # North Carolina
    "CHARLOTTE": "NC", "RALEIGH": "NC", "GREENSBORO": "NC", "DURHAM": "NC",
    # Michigan
    "DETROIT": "MI", "GRAND RAPIDS": "MI", "WARREN": "MI", "STERLING HEIGHTS": "MI",
    # Arizona
    "PHOENIX": "AZ", "TUCSON": "AZ", "MESA": "AZ", "CHANDLER": "AZ", "SCOTTSDALE": "AZ",
    # Washington
    "SEATTLE": "WA", "SPOKANE": "WA", "TACOMA": "WA",
    # Massachusetts
    "BOSTON": "MA", "WORCESTER": "MA", "SPRINGFIELD": "MA",
    # Tennessee
    "NASHVILLE": "TN", "MEMPHIS": "TN", "KNOXVILLE": "TN",
    # Indiana
    "INDIANAPOLIS": "IN", "FORT WAYNE": "IN", "EVANSVILLE": "IN",
    # Missouri
    "KANSAS CITY": "MO", "ST LOUIS": "MO", "SAINT LOUIS": "MO", "SPRINGFIELD MO": "MO",
    # Maryland
    "BALTIMORE": "MD",
    # Wisconsin
    "MILWAUKEE": "WI", "MADISON": "WI",
    # Colorado
    "DENVER": "CO", "COLORADO SPRINGS": "CO", "AURORA CO": "CO",
    # Nevada
    "LAS VEGAS": "NV", "HENDERSON": "NV", "RENO": "NV",
    # Oregon
    "PORTLAND": "OR", "SALEM": "OR", "EUGENE": "OR",
    # Minnesota
    "MINNEAPOLIS": "MN", "ST PAUL": "MN", "SAINT PAUL": "MN",
    # Louisiana
    "NEW ORLEANS": "LA", "BATON ROUGE": "LA", "SHREVEPORT": "LA",
    # Hawaii
    "HONOLULU": "HI", "HILO": "HI",
    # Alaska
    "ANCHORAGE": "AK", "FAIRBANKS": "AK", "JUNEAU": "AK",
}

# 2-letter abbreviations that are ALSO common English words — never match these
# as standalone words unless the full input is just that abbreviation.
AMBIGUOUS_ABBRS = {"IN", "OR", "ME", "HI", "OK", "OH", "IA", "ID", "AR", "MT", "WA", "MA", "PA", "DE", "LA", "CO", "AL", "MO"}


def normalize_state(state_input: str) -> str | None:
    """
    Convert a state name, abbreviation, or city name to a 2-letter state code.
    Returns None if not recognized.

    Matching priority:
    1. Full state name (e.g., "California")
    2. City name (e.g., "Fresno" → "CA")
    3. Unambiguous 2-letter abbreviation (e.g., "CA", "TX")
    4. Ambiguous 2-letter abbreviation ONLY if it's the entire input (e.g., user said just "IN")
    """
    s = state_input.strip().upper()

    # 1. Full state name
    if s in NAME_TO_ABBR:
        return NAME_TO_ABBR[s]

    # 2. City name (try multi-word first, then single word)
    if s in CITY_TO_STATE:
        return CITY_TO_STATE[s]

    # 3. Unambiguous 2-letter abbreviation — only if it's the whole token
    if len(s) == 2 and s in NAME_TO_ABBR.values():
        if s not in AMBIGUOUS_ABBRS:
            return s
        # Ambiguous abbr: only match if this is the entire user input (handled in caller)

    return None


def extract_state_from_utterance(utterance: str) -> str | None:
    """
    Attempts to extract a US state from a free-form utterance.
    Much safer than splitting on words and checking each token.

    Strategy:
    1. Check for full state name anywhere in the utterance
    2. Check for city name anywhere in the utterance
    3. Only match a 2-letter abbreviation if it's the ENTIRE utterance
       (after stripping punctuation), to avoid "in" → Indiana etc.
    """
    u = utterance.strip()
    u_upper = u.upper()

    # 1. Full state name — check as substring
    for name, abbr in NAME_TO_ABBR.items():
        if re.search(r'\b' + re.escape(name) + r'\b', u_upper):
            return abbr

    # 2. City name — longest match first to avoid "LA" matching before "LOS ANGELES"
    sorted_cities = sorted(CITY_TO_STATE.keys(), key=len, reverse=True)
    for city in sorted_cities:
        if re.search(r'\b' + re.escape(city) + r'\b', u_upper):
            return CITY_TO_STATE[city]

    # 3. Standalone abbreviation — only if the entire cleaned input is the abbr
    cleaned = re.sub(r'[^A-Z]', '', u_upper)
    if len(cleaned) == 2 and cleaned in NAME_TO_ABBR.values():
        return cleaned

    return None


def get_state_rules(state_input: str) -> dict:
    with open(RULES_PATH) as f:
        rules = json.load(f)
    abbr = normalize_state(state_input)
    if abbr and abbr in rules:
        return {"state_code": abbr, **rules[abbr]}
    return {"state_code": "UNKNOWN", **rules["DEFAULT"]}


def format_rules_for_prompt(state_input: str) -> str:
    rules = get_state_rules(state_input)
    return (
        f"State: {rules['name']}\n"
        f"Minimum age for primary policyholder: {rules['min_primary_age']}\n"
        f"Maximum age for a dependent: {rules['max_dependent_age']}"
    )


def is_valid_us_state(state_input: str) -> bool:
    return normalize_state(state_input) is not None


if __name__ == "__main__":
    # Test cases
    tests = [
        ("I live in Fresno", "CA"),
        ("California", "CA"),
        ("IN", "IN"),           # standalone abbreviation — should match Indiana
        ("I live in Indiana", "IN"),  # full name — should match
        ("my name is in California", "CA"),  # "in" should NOT match Indiana
        ("New York", "NY"),
        ("I'm in Chicago", "IL"),
        ("Las Vegas", "NV"),
        ("France", None),
    ]
    for utterance, expected in tests:
        result = extract_state_from_utterance(utterance)
        status = "✓" if result == expected else "✗"
        print(f"{status} '{utterance}' → {result} (expected {expected})")
