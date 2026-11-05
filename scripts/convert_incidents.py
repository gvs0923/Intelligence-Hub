"""Convert kubernetes-failure-stories README entries into incidents JSON.

Source: https://codeberg.org/hjacobs/kubernetes-failure-stories (CC BY-SA 4.0)
Each README entry looks like:

* [Title - Org - kind year](https://link)
    * involved: component, component
    * impact: what broke
"""

import argparse
import json
import re
from pathlib import Path

from pydantic import ValidationError

from src.ingestion.incident_models import IncidentRecord

ENTRY_RE = re.compile(
    r"^\* \[(?P<title>[^\]]+)\]\((?P<link>[^)]+)\)\s*\n"
    r"(?P<details>(?:\s{4}\* .*\n?)*)",
    re.MULTILINE,
)
DETAIL_RE = re.compile(r"^\s{4}\* (?P<key>\w+):\s*(?P<value>.*)$", re.MULTILINE)


def parse_entries(readme: str) -> list[dict]:
    records = []
    for i, match in enumerate(ENTRY_RE.finditer(readme), start=1):
        title = match.group("title").strip()
        link = match.group("link").strip()
        details = {
            m.group("key"): m.group("value").strip().strip("`")
            for m in DETAIL_RE.finditer(match.group("details"))
        }
        parts = [f"Source: {link}"]
        if details.get("involved"):
            parts.append(f"Involved components: {details['involved']}.")
        if details.get("impact"):
            parts.append(f"Impact: {details['impact']}.")
        records.append(
            {
                "id": f"k8saf-{i:03d}",
                "title": title,
                "description": " ".join(parts)[:2000],
                "severity": None,
            }
        )
    return records


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--readme",
        default="/tmp/k8s-af-cb/README.md",
        help="Path to kubernetes-failure-stories README.md",
    )
    parser.add_argument("--out", default="corpus/incidents.json")
    args = parser.parse_args()

    readme = Path(args.readme).read_text()
    records, skipped = [], 0
    for raw in parse_entries(readme):
        try:
            records.append(IncidentRecord.model_validate(raw).model_dump(mode="json"))
        except ValidationError:
            skipped += 1

    Path(args.out).parent.mkdir(parents=True, exist_ok=True)
    Path(args.out).write_text(json.dumps(records, indent=2) + "\n")
    print(f"wrote {len(records)} incidents to {args.out} ({skipped} skipped)")


if __name__ == "__main__":
    main()
