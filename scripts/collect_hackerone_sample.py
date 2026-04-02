#!/usr/bin/env python3

from __future__ import annotations

import argparse
import csv
import json
import re
import statistics
import time
from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path
from typing import Any

import requests


GRAPHQL_URL = "https://hackerone.com/graphql"
LEADERBOARD_URL = "https://hackerone.com/leaderboard"
USER_AGENT = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/135.0.0.0 Safari/537.36"


HIGHEST_REPUTATION_LEADERBOARD_QUERY = """
query HighestReputationLeaderboardCard($year: Int!, $first: Int, $key: LeaderboardKeyEnum!) {
  leaderboard_entries(key: $key, year: $year, first: $first) {
    edges {
      node {
        __typename
        ... on HighestReputationLeaderboardEntry {
          id
          rank
          previous_rank
          reputation
          signal
          impact
          user {
            id
            username
            profile_picture(size: medium)
            mark_as_company_on_leaderboards
          }
        }
      }
    }
  }
}
""".strip()


ALL_TIME_REPUTATION_LEADERBOARD_QUERY = """
query AllTimeReputationLeaderboardCard($first: Int, $key: LeaderboardKeyEnum!) {
  leaderboard_entries(key: $key, first: $first) {
    edges {
      node {
        __typename
        ... on AllTimeReputationLeaderboardEntry {
          id
          rank
          reputation
          user {
            id
            username
            mark_as_company_on_leaderboards
            signal
            impact
          }
        }
      }
    }
  }
}
""".strip()


PROFILE_ENRICHMENT_QUERY = """
query ProfileEnrichment(
  $username: String!,
  $pageSize: Int!,
  $snapshot90: UserStatisticsSnapshotTypeEnum!,
  $snapshotYear: UserStatisticsSnapshotTypeEnum!
) {
  user(username: $username) {
    id
    username
    name
    created_at
    location
    website
    bio
    intro
    profile_activated
    bugcrowd_handle
    hack_the_box_handle
    github_handle
    gitlab_handle
    linkedin_handle
    twitter_handle
    cleared
    verified
    open_for_employment
    mark_as_company_on_leaderboards
    signal
    signal_percentile
    impact
    impact_percentile
    reputation
    rank
    resolved_report_count
    thanks_items_total_count
    public_reviews(first: 5) {
      edges {
        node {
          id
          public_feedback
          team {
            id
            name
            handle
          }
        }
      }
    }
    user_streak {
      id
      length
      start_date
      end_date
    }
    hacker_skills(where: { skill: { approved: { _eq: true } } }) {
      nodes {
        id
        skill {
          id
          database_id: _id
          name
        }
      }
    }
    pentester_profile {
      id
      name
      completed_pentests_number
      certifications: certifications_pentester_profiles(first: 5) {
        edges {
          node {
            id
            certification {
              id
              name
              short_name
            }
            certification_identifier
            starts_at
            ends_at
          }
        }
      }
    }
    badges(first: 3) {
      edges {
        awarded_at
        node {
          id
          name
          image_path
        }
      }
    }
    memberships(first: 10, where: { concealed: { _eq: false } }) {
      total_count
      edges {
        node {
          id
          team {
            id
            name
            handle
            state
            url
          }
        }
      }
    }
    thanks_items(first: $pageSize) {
      pageInfo {
        hasNextPage
        endCursor
      }
      edges {
        node {
          id
          rank
          report_count
          total_report_count
          reputation
          team {
            id
            name
            handle
            state
            url
          }
        }
      }
    }
    testimonials(
      first: 5,
      where: { visible_on_user_profile: { _eq: true } },
      order_by: { survey_rating: { completed_at: { _direction: DESC } } }
    ) {
      pageInfo {
        endCursor
        hasNextPage
      }
      edges {
        node {
          id
          key
          rating
          public_comment
          survey_rating {
            id
            type
            completed_at
            created_at
            team {
              id
              name
            }
          }
        }
      }
    }
    stats90: statistics_snapshot(snapshot_type: $snapshot90) {
      id
      signal
      signal_percentile
      impact
      impact_percentile
      reputation
      rank
    }
    statsYear: statistics_snapshot(snapshot_type: $snapshotYear) {
      id
      signal
      signal_percentile
      impact
      impact_percentile
      reputation
      rank
    }
  }
}
""".strip()


@dataclass
class SampleConfig:
    year: int
    reference_date: date
    current_top: int
    veterans: int
    leaderboard_limit: int
    profile_page_size: int
    sleep_seconds: float
    output_root: Path


def build_session() -> requests.Session:
    session = requests.Session()
    bootstrap_response = session.get(
        LEADERBOARD_URL,
        headers={"User-Agent": USER_AGENT},
        timeout=30,
    )
    bootstrap_response.raise_for_status()
    csrf_match = re.search(
        r'<meta name="csrf-token" content="([^"]+)"',
        bootstrap_response.text,
    )
    if not csrf_match:
        raise RuntimeError("Не удалось извлечь CSRF token из HackerOne.")

    session.headers.update(
        {
            "User-Agent": USER_AGENT,
            "Content-Type": "application/json",
            "X-CSRF-Token": csrf_match.group(1),
            "X-Requested-With": "XMLHttpRequest",
        }
    )
    return session


def graphql(session: requests.Session, query: str, variables: dict[str, Any]) -> dict[str, Any]:
    response = session.post(
        GRAPHQL_URL,
        json={"query": query, "variables": variables},
        timeout=30,
    )
    response.raise_for_status()
    payload = response.json()
    if payload.get("errors"):
        raise RuntimeError(json.dumps(payload["errors"], ensure_ascii=False, indent=2))
    return payload["data"]


def fetch_highest_reputation_leaderboard(
    session: requests.Session,
    year: int,
    limit: int,
) -> list[dict[str, Any]]:
    data = graphql(
        session,
        HIGHEST_REPUTATION_LEADERBOARD_QUERY,
        {"year": year, "first": limit, "key": "HIGHEST_REPUTATION"},
    )
    entries = []
    for edge in data["leaderboard_entries"]["edges"]:
        node = edge["node"]
        user = node["user"]
        entries.append(
            {
                "username": user["username"],
                "rank": node["rank"],
                "previous_rank": node["previous_rank"],
                "reputation": node["reputation"],
                "signal": node["signal"],
                "impact": node["impact"],
                "user_id": user["id"],
            }
        )
    return entries


def fetch_all_time_reputation_leaderboard(
    session: requests.Session,
    limit: int,
) -> list[dict[str, Any]]:
    data = graphql(
        session,
        ALL_TIME_REPUTATION_LEADERBOARD_QUERY,
        {"first": limit, "key": "ALL_TIME_REPUTATION"},
    )
    entries = []
    for edge in data["leaderboard_entries"]["edges"]:
        node = edge["node"]
        user = node["user"]
        entries.append(
            {
                "username": user["username"],
                "rank": node["rank"],
                "reputation": node["reputation"],
                "signal": user["signal"],
                "impact": user["impact"],
                "user_id": user["id"],
            }
        )
    return entries


def fetch_profile(
    session: requests.Session,
    username: str,
    page_size: int,
) -> dict[str, Any]:
    data = graphql(
        session,
        PROFILE_ENRICHMENT_QUERY,
        {
            "username": username,
            "pageSize": page_size,
            "snapshot90": "last_90_days",
            "snapshotYear": "past_year",
        },
    )
    return data["user"]


def normalize_text(value: Any) -> Any:
    if not isinstance(value, str):
        return value
    cleaned = value.strip()
    return cleaned or None


def iso_to_date(value: str | None) -> str | None:
    if not value:
        return None
    return value[:10]


def month_delta(reference: date, other: date) -> int:
    return (reference.year - other.year) * 12 + (reference.month - other.month)


def is_recent_streak(end_date: str | None, reference_date: date) -> bool:
    if not end_date:
        return False
    end = datetime.fromisoformat(end_date.replace("Z", "+00:00")).date()
    delta = month_delta(reference_date, end)
    return 0 <= delta <= 1


def list_skills(profile: dict[str, Any]) -> list[str]:
    nodes = profile.get("hacker_skills", {}).get("nodes", [])
    return sorted(
        {
            node["skill"]["name"]
            for node in nodes
            if node.get("skill") and normalize_text(node["skill"].get("name"))
        }
    )


def list_certifications(profile: dict[str, Any]) -> list[str]:
    pentester_profile = profile.get("pentester_profile") or {}
    edges = pentester_profile.get("certifications", {}).get("edges", [])
    return [
        edge["node"]["certification"]["short_name"]
        or edge["node"]["certification"]["name"]
        for edge in edges
        if edge.get("node") and edge["node"].get("certification")
    ]


def list_memberships(profile: dict[str, Any]) -> list[str]:
    edges = profile.get("memberships", {}).get("edges", [])
    names = []
    for edge in edges:
        team = edge.get("node", {}).get("team")
        if not team:
            continue
        if team.get("name"):
            names.append(team["name"])
        elif team.get("handle"):
            names.append(team["handle"])
    return names


def list_thanks_programs(profile: dict[str, Any]) -> list[str]:
    edges = profile.get("thanks_items", {}).get("edges", [])
    programs = []
    for edge in edges:
        team = edge.get("node", {}).get("team")
        if team and team.get("name"):
            programs.append(team["name"])
        else:
            programs.append("Private Program")
    return programs


def latest_badge_awarded_at(profile: dict[str, Any]) -> str | None:
    edges = profile.get("badges", {}).get("edges", [])
    if not edges:
        return None
    dates = [edge["awarded_at"] for edge in edges if edge.get("awarded_at")]
    return iso_to_date(max(dates)) if dates else None


def count_public_reviews(profile: dict[str, Any]) -> int:
    return len(profile.get("public_reviews", {}).get("edges", []))


def count_testimonials(profile: dict[str, Any]) -> int:
    return len(profile.get("testimonials", {}).get("edges", []))


def rank_score(rank: int | None, limit: int = 100) -> float:
    if not rank or rank > limit:
        return 0.0
    return max(0.0, (limit + 1 - rank) / limit)


def capped_score(value: float | int | None, cap: float) -> float:
    if value is None:
        return 0.0
    return min(float(value) / cap, 1.0)


def derive_segment(current_rank: int | None, all_time_rank: int | None) -> str:
    if current_rank and current_rank <= 10 and all_time_rank and all_time_rank <= 10:
        return "elite_active"
    if current_rank and current_rank <= 10:
        return "active_riser"
    if all_time_rank and all_time_rank <= 10:
        return "established_veteran"
    return "watchlist"


def derive_priority_score(row: dict[str, Any]) -> float:
    score = 0.0
    score += rank_score(row.get("current_year_rank")) * 30
    score += rank_score(row.get("all_time_rank")) * 20
    score += capped_score(row.get("past_year_reputation"), 5000) * 20
    score += capped_score(row.get("resolved_report_count"), 1000) * 15
    score += capped_score(row.get("thanks_items_total_count"), 150) * 10
    score += capped_score(row.get("streak_length"), 12) * 5
    return round(score, 2)


def flatten_profile(
    username: str,
    selection_bucket: str,
    current_year_lookup: dict[str, dict[str, Any]],
    all_time_lookup: dict[str, dict[str, Any]],
    profile: dict[str, Any],
    reference_date: date,
) -> dict[str, Any]:
    current_year_entry = current_year_lookup.get(username, {})
    all_time_entry = all_time_lookup.get(username, {})
    stats90 = profile.get("stats90") or {}
    stats_year = profile.get("statsYear") or {}
    streak = profile.get("user_streak") or {}

    row = {
        "username": username,
        "name": normalize_text(profile.get("name")),
        "selection_bucket": selection_bucket,
        "current_year_rank": current_year_entry.get("rank"),
        "current_year_previous_rank": current_year_entry.get("previous_rank"),
        "current_year_reputation": current_year_entry.get("reputation"),
        "all_time_rank": all_time_entry.get("rank"),
        "all_time_reputation": all_time_entry.get("reputation"),
        "all_time_signal": profile.get("signal"),
        "all_time_signal_percentile": profile.get("signal_percentile"),
        "all_time_impact": profile.get("impact"),
        "all_time_impact_percentile": profile.get("impact_percentile"),
        "platform_reputation": profile.get("reputation"),
        "platform_rank": profile.get("rank"),
        "last_90d_reputation": stats90.get("reputation"),
        "last_90d_rank": stats90.get("rank"),
        "last_90d_signal": stats90.get("signal"),
        "last_90d_impact": stats90.get("impact"),
        "past_year_reputation": stats_year.get("reputation"),
        "past_year_rank": stats_year.get("rank"),
        "past_year_signal": stats_year.get("signal"),
        "past_year_impact": stats_year.get("impact"),
        "resolved_report_count": profile.get("resolved_report_count"),
        "thanks_items_total_count": profile.get("thanks_items_total_count"),
        "streak_length": streak.get("length"),
        "streak_start_date": iso_to_date(streak.get("start_date")),
        "streak_end_date": iso_to_date(streak.get("end_date")),
        "streak_recent": is_recent_streak(streak.get("end_date"), reference_date),
        "memberships_total": profile.get("memberships", {}).get("total_count"),
        "completed_pentests_number": (
            profile.get("pentester_profile", {}) or {}
        ).get("completed_pentests_number"),
        "skills_count": len(list_skills(profile)),
        "skills": ", ".join(list_skills(profile)),
        "certifications_count": len(list_certifications(profile)),
        "certifications": ", ".join(list_certifications(profile)),
        "public_review_count": count_public_reviews(profile),
        "testimonial_count": count_testimonials(profile),
        "recent_badges_count": len(profile.get("badges", {}).get("edges", [])),
        "latest_badge_awarded_at": latest_badge_awarded_at(profile),
        "top_thanks_programs": " | ".join(list_thanks_programs(profile)),
        "visible_membership_programs": " | ".join(list_memberships(profile)),
        "verified": profile.get("verified"),
        "cleared": profile.get("cleared"),
        "open_for_employment": profile.get("open_for_employment"),
        "location": normalize_text(profile.get("location")),
        "website": normalize_text(profile.get("website")),
        "created_at": iso_to_date(profile.get("created_at")),
    }
    row["segment"] = derive_segment(row["current_year_rank"], row["all_time_rank"])
    row["has_recent_public_signal"] = bool(
        row["current_year_rank"] or row["last_90d_reputation"] or row["streak_recent"]
    )
    row["priority_score"] = derive_priority_score(row)
    return row


def summarize_rows(rows: list[dict[str, Any]], config: SampleConfig) -> dict[str, Any]:
    numeric_fields = [
        "priority_score",
        "current_year_reputation",
        "all_time_reputation",
        "past_year_reputation",
        "resolved_report_count",
        "thanks_items_total_count",
        "streak_length",
    ]

    def median_for(field: str) -> float | None:
        values = [row[field] for row in rows if isinstance(row.get(field), (int, float))]
        return round(statistics.median(values), 2) if values else None

    top_priority = sorted(rows, key=lambda row: row["priority_score"], reverse=True)
    segment_counts: dict[str, int] = {}
    for row in rows:
        segment_counts[row["segment"]] = segment_counts.get(row["segment"], 0) + 1

    return {
        "reference_date": config.reference_date.isoformat(),
        "leaderboard_year": config.year,
        "sample_size": len(rows),
        "usernames": [row["username"] for row in rows],
        "segment_counts": segment_counts,
        "recent_public_signal_count": sum(1 for row in rows if row["has_recent_public_signal"]),
        "medians": {field: median_for(field) for field in numeric_fields},
        "top_priority": [
            {
                "username": row["username"],
                "segment": row["segment"],
                "priority_score": row["priority_score"],
                "current_year_rank": row["current_year_rank"],
                "all_time_rank": row["all_time_rank"],
            }
            for row in top_priority[:5]
        ],
    }


def write_json(path: Path, payload: Any) -> None:
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    if not rows:
        raise RuntimeError("Нет данных для записи CSV.")
    with path.open("w", newline="", encoding="utf-8") as file_handle:
        writer = csv.DictWriter(file_handle, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)


def select_sample(
    current_year_entries: list[dict[str, Any]],
    all_time_entries: list[dict[str, Any]],
    config: SampleConfig,
) -> list[dict[str, str]]:
    selected: list[dict[str, str]] = []
    selected_usernames: set[str] = set()

    for entry in current_year_entries[: config.current_top]:
        selected.append(
            {"username": entry["username"], "selection_bucket": "current_year_top"}
        )
        selected_usernames.add(entry["username"])

    for entry in all_time_entries:
        if len([item for item in selected if item["selection_bucket"] == "all_time_veteran"]) >= config.veterans:
            break
        if entry["username"] in selected_usernames:
            continue
        selected.append(
            {"username": entry["username"], "selection_bucket": "all_time_veteran"}
        )
        selected_usernames.add(entry["username"])

    return selected


def parse_args() -> SampleConfig:
    parser = argparse.ArgumentParser(
        description="Collect a reproducible public sample of active and valuable HackerOne bug hunters.",
    )
    parser.add_argument("--year", type=int, default=date.today().year)
    parser.add_argument("--reference-date", default=date.today().isoformat())
    parser.add_argument("--current-top", type=int, default=15)
    parser.add_argument("--veterans", type=int, default=5)
    parser.add_argument("--leaderboard-limit", type=int, default=100)
    parser.add_argument("--profile-page-size", type=int, default=5)
    parser.add_argument("--sleep-seconds", type=float, default=0.35)
    parser.add_argument("--output-root", default="data")
    args = parser.parse_args()

    return SampleConfig(
        year=args.year,
        reference_date=date.fromisoformat(args.reference_date),
        current_top=args.current_top,
        veterans=args.veterans,
        leaderboard_limit=args.leaderboard_limit,
        profile_page_size=args.profile_page_size,
        sleep_seconds=args.sleep_seconds,
        output_root=Path(args.output_root),
    )


def main() -> None:
    config = parse_args()
    raw_dir = config.output_root / "raw"
    processed_dir = config.output_root / "processed"
    raw_dir.mkdir(parents=True, exist_ok=True)
    processed_dir.mkdir(parents=True, exist_ok=True)

    session = build_session()
    current_year_entries = fetch_highest_reputation_leaderboard(
        session,
        config.year,
        config.leaderboard_limit,
    )
    all_time_entries = fetch_all_time_reputation_leaderboard(
        session,
        config.leaderboard_limit,
    )

    current_year_lookup = {entry["username"]: entry for entry in current_year_entries}
    all_time_lookup = {entry["username"]: entry for entry in all_time_entries}
    sample = select_sample(current_year_entries, all_time_entries, config)

    profiles_raw: dict[str, dict[str, Any]] = {}
    rows: list[dict[str, Any]] = []
    for index, item in enumerate(sample, start=1):
        username = item["username"]
        profile = fetch_profile(session, username, config.profile_page_size)
        profiles_raw[username] = profile
        rows.append(
            flatten_profile(
                username=username,
                selection_bucket=item["selection_bucket"],
                current_year_lookup=current_year_lookup,
                all_time_lookup=all_time_lookup,
                profile=profile,
                reference_date=config.reference_date,
            )
        )
        if index < len(sample):
            time.sleep(config.sleep_seconds)

    rows.sort(key=lambda row: row["priority_score"], reverse=True)
    summary = summarize_rows(rows, config)

    write_json(raw_dir / "leaderboard_highest_reputation_current_year.json", current_year_entries)
    write_json(raw_dir / "leaderboard_all_time_reputation.json", all_time_entries)
    write_json(raw_dir / "selected_sample.json", sample)
    write_json(raw_dir / "profiles_raw.json", profiles_raw)

    write_json(processed_dir / "hunters_sample.json", rows)
    write_csv(processed_dir / "hunters_sample.csv", rows)
    write_json(processed_dir / "hunters.json", rows)
    write_csv(processed_dir / "hunters.csv", rows)
    write_json(processed_dir / "summary.json", summary)
    write_json(Path("hunters.json"), rows)
    write_csv(Path("hunters.csv"), rows)

    print(
        json.dumps(
            {
                "reference_date": config.reference_date.isoformat(),
                "year": config.year,
                "sample_size": len(rows),
                "top_priority_usernames": [row["username"] for row in rows[:5]],
            },
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
