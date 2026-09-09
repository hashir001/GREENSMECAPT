"""Build observations from policy, company and response JSON files."""

import argparse
import json
from pathlib import Path

from greensmecapt.assessment.observations import CriterionResponse, build_observations
from greensmecapt.assessment.profiles import (
    AssessmentContext,
    build_profile,
    load_policy,
)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("policy", type=Path)
    parser.add_argument("company", type=Path)
    parser.add_argument("responses", type=Path)
    args = parser.parse_args()
    try:
        policy = load_policy(args.policy)
        context = AssessmentContext.model_validate_json(
            args.company.read_text(encoding="utf-8")
        )
        response_data = json.loads(args.responses.read_text(encoding="utf-8"))
        responses = tuple(
            CriterionResponse.model_validate(item) for item in response_data
        )
        result = build_observations(build_profile(context, policy), responses=responses)
    except (ValueError, OSError) as error:
        parser.exit(2, f"Observations could not be built: {error}\n")
    print(result.model_dump_json(indent=2))


if __name__ == "__main__":
    main()
