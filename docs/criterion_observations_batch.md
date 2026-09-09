# Criterion observations batch

This batch joins the tailored activity profile to applicant responses and reviewed
document evidence. It still does **not** assign a criterion score or an MCDM rank.

The important states remain different:

- unknown: no usable answer is available;
- not measured: the topic applies, but the SME does not currently measure it;
- not applicable: the profile or a reviewed override resolved it out;
- applicability review: the applicant claimed N/A or activity facts are unresolved;
- pending review: extraction exists but has not been accepted;
- conflict or needs selection: sources cannot safely be combined;
- ready numeric, range or linguistic: an explicit input exists for a later,
  versioned normalization rule.

An accepted `renewable_energy_percentage` is mapped to the purchased-energy topic,
but remains a named source indicator. `72%` is never silently converted into a
purchased-energy criterion score.

Run the example after applying the patch:

```bash
python -m greensmecapt.assessment.observations \
  config/assessment_profiles.development.json \
  examples/assessment_profiles/small_manufacturer.json \
  examples/assessment_profiles/small_manufacturer_responses.json
```

The next layer will define versioned normalization and comparability rules. Only
that layer may turn suitable observations into MCDM inputs.
