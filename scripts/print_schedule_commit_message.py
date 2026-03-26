#!/usr/bin/env python3

from schedule_common import OUTPUT_DIR, load_week_payload


def build_commit_message(manifest):
    current_start = manifest["current_week"]["start"]
    next_start = manifest["next_week"]["start"]
    next_event_count = manifest["next_week"].get("event_count", 0)
    return (
        f"Refresh schedule assets for {current_start} and {next_start} "
        f"({next_event_count} next-week events)"
    )


def main():
    manifest = load_week_payload(OUTPUT_DIR / "manifest.json")
    print(build_commit_message(manifest))


if __name__ == "__main__":
    main()
