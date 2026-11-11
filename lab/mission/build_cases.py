"""Copy real saved head calls into a portable, source-labelled corpus."""

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent


def main():
    cases = []
    for session in ("20261110-230229", "20261110-231512"):
        source = Path("/Users/kerim/recordings/pilot") / session / "head.jsonl"
        for line_number, line in enumerate(source.read_text().splitlines(), 1):
            row = json.loads(line)
            if row.get("type") != "response" or not row.get("plan"):
                continue
            cases.append(
                {
                    "id": f"pilot-{session}-{row['id']:02d}",
                    "provenance": "saved_head_request_and_model_answer",
                    "source": {"path": str(source), "line": line_number},
                    "request": row["request"],
                    "model": {key: row[key] for key in ("plan", "sentence", "lesson") if key in row},
                }
            )
    (ROOT / "saved_cases.json").write_text(json.dumps(cases, ensure_ascii=False, indent=2) + "\n")
    print(f"Saved {len(cases)} unmodified requests and model answers")


if __name__ == "__main__":
    main()
