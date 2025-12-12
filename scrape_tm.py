#!/usr/bin/env python3
"""
scrape_transfermarkt_teams.py
Usage:
  python scrape_transfermarkt_teams.py --url "https://www.transfermarkt.com/..."
  python scrape_transfermarkt_teams.py --file teams.txt --combined combined.csv
teams.txt is a newline-separated list of Transfermarkt team pages.
"""

import argparse
import random
import re
import sys
import time
from urllib.parse import urljoin

import pandas as pd
import requests
from bs4 import BeautifulSoup
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"
    " AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
}


def build_session(retries=3, backoff_factor=0.5, status_forcelist=(500, 502, 503, 504)):
    s = requests.Session()
    retry = Retry(
        total=retries,
        read=retries,
        connect=retries,
        backoff_factor=backoff_factor,
        status_forcelist=status_forcelist,
        allowed_methods=frozenset(["GET", "POST"]),
    )
    adapter = HTTPAdapter(max_retries=retry)
    s.mount("https://", adapter)
    s.mount("http://", adapter)
    s.headers.update(HEADERS)
    return s


def get_soup(session, url, sleep=True):
    if sleep:
        time.sleep(random.uniform(1.0, 2.0))
    resp = session.get(url, timeout=15)
    resp.raise_for_status()
    return BeautifulSoup(resp.text, "lxml")


def get_player_details(session, player_url):
    """Return dict with height, foot, debut (best-effort)"""
    try:
        soup = get_soup(session, player_url)
    except Exception as e:
        return {"height": "N/A", "foot": "N/A", "debut": "N/A"}

    details = {"height": "N/A", "foot": "N/A", "debut": "N/A"}

    # Try common patterns for height like "1,85 m" or "185 cm"
    text = soup.get_text(separator=" ", strip=True)
    m = re.search(r"\b\d[,\.]\d{2}\s*m\b", text)
    if not m:
        m = re.search(r"\b\d{3}\s*cm\b", text)
    if m:
        details["height"] = m.group(0)

    # Foot (try label search)
    foot_labels = soup.find_all(
        string=re.compile(r"(foot|strong foot|preferred foot)", re.I)
    )
    for label in foot_labels:
        parent = label.find_parent()
        if parent:
            # look nearby
            sibling = parent.find_next(string=True)
            if sibling:
                s = sibling.strip().lower()
                if s in ("right", "left", "both"):
                    details["foot"] = s
                    break
    # fallback simple search
    if details["foot"] == "N/A":
        if re.search(r"\b(right|left|both)\s+foot\b", text, re.I):
            ff = re.search(r"\b(right|left|both)\s+foot\b", text, re.I).group(1)
            details["foot"] = ff

    # Debut: best-effort search for a date near 'national team' or 'Morocco' words.
    # This is heuristic — Transfermarkt structures vary.
    if re.search(r"\b(Morocco|Maroc)\b", text, re.I):
        # find date patterns
        md = re.search(
            r"\b(?:\d{1,2}[./]\d{1,2}[./]\d{2,4}|\w{3,}\s+\d{1,2},\s+\d{4})\b", text
        )
        if md:
            details["debut"] = md.group(0)

    return details


def scrape_team(session, team_url):
    print(f"Fetching team page: {team_url}")
    soup = get_soup(session, team_url, sleep=False)
    # Team name for file naming
    title = soup.title.string if soup.title else "team"
    team_name = re.sub(r"\W+", "_", title).strip("_")[:50]

    table = soup.find("table", {"class": "items"})
    if not table:
        print("  Could not find team table on page (structure changed?). Skipping.")
        return None, []

    rows = table.find_all("tr", {"class": ["odd", "even"]})
    players = []
    total = len(rows)
    for idx, row in enumerate(rows, 1):
        try:
            # name
            name_td = row.find("td", {"class": "hauptlink"})
            name = name_td.get_text(strip=True) if name_td else "N/A"

            # age & position & market value
            zent = row.find_all("td", {"class": "zentriert"})
            age = zent[1].get_text(strip=True) if len(zent) > 1 else "N/A"

            # position: sometimes inside nested table
            pos_tag = row.find("td", {"class": "zentriert"})
            position = ""
            if pos_tag:
                tbl = pos_tag.find("table")
                if tbl:
                    position = tbl.get_text(strip=True)

            mv_tag = row.find("td", {"class": "rechts hauptlink"})
            market_value = mv_tag.get_text(strip=True) if mv_tag else "N/A"

            # profile link
            player_link_tag = name_td.find("a") if name_td else None
            player_url = (
                urljoin("https://www.transfermarkt.com", player_link_tag.get("href"))
                if player_link_tag and player_link_tag.get("href")
                else None
            )

            details = {"height": "N/A", "foot": "N/A", "debut": "N/A"}
            if player_url:
                print(f"  [{idx}/{total}] {name} -> details...", end="")
                details = get_player_details(session, player_url)
                status = []
                if details["height"] != "N/A":
                    status.append(f"H:{details['height']}")
                if details["foot"] != "N/A":
                    status.append(f"F:{details['foot']}")
                if details["debut"] != "N/A":
                    status.append("D:✓")
                if status:
                    print(" [" + ", ".join(status) + "]")
                else:
                    print(" [no extra]")
            else:
                print(f"  [{idx}/{total}] {name} - no profile link")

            players.append(
                {
                    "name": name,
                    "age": age,
                    "position": position,
                    "height": details["height"],
                    "foot": details["foot"],
                    "debut": details["debut"],
                    "market_value": market_value,
                }
            )
        except Exception as e:
            print(f"   ✗ error on row {idx}: {e}")
            continue
    return team_name, players


def main():
    parser = argparse.ArgumentParser()
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--url", help="Single Transfermarkt team URL")
    group.add_argument("--file", help="File with one Transfermarkt team URL per line")
    parser.add_argument(
        "--combined", help="Optional combined CSV filename (e.g. all_teams.csv)"
    )
    args = parser.parse_args()

    session = build_session()
    all_players = []

    urls = []
    if args.url:
        urls = [args.url.strip()]
    else:
        with open(args.file, "r", encoding="utf-8") as f:
            urls = [line.strip() for line in f if line.strip()]

    for url in urls:
        team_name, players = scrape_team(session, url)
        if team_name and players:
            out_name = f"{team_name}.csv"
            df = pd.DataFrame(players)
            df.to_csv(out_name, index=False, encoding="utf-8-sig")
            print(f"  ✓ Saved {len(players)} players to {out_name}")
            # annotate with team
            df["team"] = team_name
            all_players.append(df)

    if args.combined and all_players:
        combined = pd.concat(all_players, ignore_index=True)
        combined.to_csv(args.combined, index=False, encoding="utf-8-sig")
        print(f"  ✓ Combined CSV saved to {args.combined}")


if __name__ == "__main__":
    main()
