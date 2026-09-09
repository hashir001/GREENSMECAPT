"""Run an assessment profile from policy and company JSON files."""

import argparse
import json
from pathlib import Path

from greensmecapt.assessment.profiles.engine import build_profile, load_policy
from greensmecapt.assessment.profiles.models import AssessmentContext


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("policy", type=Path)
    parser.add_argument("company", type=Path)
    parser.add_argument("--json", action="store_true", dest="as_json")
    args = parser.parse_args()
    try:
        policy = load_policy(args.policy)
        context = AssessmentContext.model_validate(
            json.loads(args.company.read_text(encoding="utf-8"))
        )
        profile = build_profile(context, policy)
    except (ValueError, OSError) as error:
        parser.exit(2, f"Profile could not be built: {error}\n")

    if args.as_json:
        print(profile.model_dump_json(indent=2))
        return

    print(f"SME: {profile.sme_id}")
    print(f"Policy: {profile.policy_id} {profile.policy_version} ({policy.status})")
    print(f"Active modules: {', '.join(profile.active_modules) or 'none confirmed'}")
    print(f"Uncertain modules: {', '.join(profile.uncertain_modules) or 'none'}")
    print("\nApplicability decisions:")
    for decision in profile.decisions:
        print(f"  {decision.status.value}: {decision.title}")
        print(f"    {decision.reason}")
    print("\nCandidate follow-ups (no message has been sent):")
    for request in profile.follow_ups:
        print(f"  {request.question}")
        print(f"    Accepted routes: {', '.join(request.response_routes)}")
    print("\nApplicability profile only; assessment scores are not calculated here.")


if __name__ == "__main__":
    main()
