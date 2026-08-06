# Keryx methodology

Keryx is a deterministic index of public United States internship and new-graduate postings. It
separates discovery, verification, extraction, and presentation so consumers can see what Keryx
knows, what it does not know, and why.

## Evidence hierarchy

1. Direct public ATS records from Greenhouse, Lever, Ashby, and Workday are preferred.
2. Structured public source metadata can supplement fields that direct text does not contain.
3. Community repositories are discovery and corroboration sources, not unquestioned authorities.

Each merged role retains source records. Conflicting observations are resolved deterministically;
direct ATS text wins over metadata for extracted requirements. Keryx never combines fragments into
a stronger claim than any source supports.

## Academic conditions

Graduation timing, current enrollment, and return-to-school conditions are extracted from available
posting text. Each condition has its own modality:

- **required** — the posting uses mandatory language;
- **preferred** — the posting presents the condition as a preference; or
- **stated** — the condition appears without enough language to classify its modality.

The conditions remain independent. A preferred graduation window is not converted into a required
window because another sentence requires current enrollment. Short evidence snippets, provenance,
the extraction version, and the date of the text check are retained.

## Role intelligence

Keryx identifies a bounded vocabulary of technical skills and role families. Title matches are
ranked above description matches. Ordinary-word technologies such as Go, Rust, React, and Swift
require contextual or case-sensitive evidence to reduce false positives.

Compensation appears only for explicit, plausible USD hourly or annual values. Work arrangement and
visa/citizenship classifications require explicit public language. When sources disagree, restrictive
citizenship or clearance language takes precedence over general sponsorship language so a permissive
sentence cannot hide a role-specific restriction.

Historical H-1B approval counts are employer-level context supplied by a public source. They are not
evidence that the current role sponsors, that the employer will sponsor in the future, or that a
particular applicant qualifies.

## Missing information

- **Not stated** means Keryx checked available posting text but did not detect the field.
- **Not available** means Keryx did not receive enough posting text to perform the check.
- **Unknown** means the available evidence does not support a conclusion.

None of these labels means an applicant is eligible. Keryx does not know applicant information and
does not generate applicant-role fit scores.

## Deliberate exclusions

Keryx does not publish speculative opening dates, predicted “drop windows,” employer prestige
rankings, inferred sponsorship, or inferred compensation. It also does not operate an email list.
Those features would weaken the evidence boundary or require collecting user data. Consumers can use
the public RSS feed for alerts without sharing an address with Keryx.

## Reproducibility

The extractors are versioned and covered by exact fixtures. Changing an extractor invalidates stale
results until a source is checked again. The generated Markdown, JSON, CSV, RSS, coverage tables, and
dashboard all derive from the same canonical `data/jobs.json` state.
