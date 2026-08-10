# Keryx

Keryx is a continuously updated database of **United States internships and new-graduate roles**.
GitHub Actions collects public listings, verifies them against direct applicant-tracking-system
feeds when possible, removes duplicates, and rebuilds the Markdown databases automatically.

## Opportunity databases

<!-- COUNTS:START -->
| Recruiting cycle | Open roles |
|---|---:|
| [Summer 2027 US Internships](internships/summer-2027.md) | 398 |
| [Fall 2026 US Internships](internships/fall-2026.md) | 454 |
| [Spring 2027 US Internships](internships/spring-2027.md) | 48 |
| [Winter 2027 US Internships](internships/winter-2027.md) | 11 |
| [US Internships — Cycle Not Stated](internships/unscheduled.md) | 442 |
| [2027 US New-Graduate Roles](new-grad/2027.md) | 627 |
| [2026 US New-Graduate Roles](new-grad/2026.md) | 43 |
| [US New-Graduate Roles — Cycle Not Stated](new-grad/unscheduled.md) | 1753 |
<!-- COUNTS:END -->

The Markdown files are the product: open them directly on GitHub, search them, bookmark them, or
consume the canonical [`data/jobs.json`](data/jobs.json) file from another program.

## Academic eligibility

Keryx shows graduation timing and related student-status conditions when they are explicitly
stated in posting text. The deterministic extractor can identify:

- graduation months, years, windows, and one-sided bounds such as “May 2027 or later”;
- current-enrollment conditions; and
- conditions about returning to school after an internship.

Every detected condition is classified independently as **required**, **preferred**, or simply
**stated** when the posting gives no clear modality. Preferred qualifications remain preferences:
Keryx never promotes them into eligibility gates. This distinction is also preserved in
`data/jobs.json` for downstream consumers.

### Current coverage

<!-- ACADEMIC-COVERAGE:START -->
| Current posting-text coverage | Open roles |
|---|---:|
| Academic condition detected | 276 |
| Text checked; no condition detected | 267 |
| Complete posting text unavailable | 3233 |

| Detected-condition modality | Criteria |
|---|---:|
| Required | 134 |
| Preferred | 10 |
| Stated without clear modality | 183 |
<!-- ACADEMIC-COVERAGE:END -->

These counts describe the current index, not applicants. A role can contribute multiple criteria
when it states more than one academic condition.

Each extracted result retains the source that supplied the text. Direct ATS text takes precedence
over community-source text. Each detected condition has its own short supporting excerpt; Keryx
does not persist the complete job description. Stored classifications include an extractor version,
so a future parser improvement invalidates stale results until the source is checked again. Every
text-backed result also records its most recent check date; metadata-only results do not claim one.

The distinction between **not stated** and **not available** is intentional. “Not stated” means
Keryx checked available posting text but did not detect academic timing language. “Not available”
means the source did not provide the complete posting text. Neither label means that every student
qualifies; applicants must confirm all requirements on the employer page.

Public Greenhouse, Lever, and Ashby descriptions currently provide most qualification coverage.
Workday search cards and community-list rows often do not include complete descriptions, so those
roles remain visibly marked “not available” rather than being guessed. The structured dates in
`data/jobs.json` are designed for future consumers such as Erga to compare against a user-approved
graduation date; Keryx itself does not know or score individual applicants.

## Sources

Keryx combines and cross-checks:

- [SimplifyJobs/Summer2027-Internships](https://github.com/SimplifyJobs/Summer2027-Internships)
- [SimplifyJobs/New-Grad-Positions](https://github.com/SimplifyJobs/New-Grad-Positions)
- [speedyapply/2027-SWE-College-Jobs](https://github.com/speedyapply/2027-SWE-College-Jobs)
- [sndsh404/summer-2027-internships](https://github.com/sndsh404/summer-2027-internships)
- [zshah101/Automated-List-Of-Summer-2027-and-Fall-2026-Tech-Internships](https://github.com/zshah101/Automated-List-Of-Summer-2027-and-Fall-2026-Tech-Internships)
- Direct public boards from Greenhouse, Ashby, Lever, and Workday

Community repositories are discovery sources. Eligible rows link to the employer's application
page, and direct ATS observations take precedence when duplicate records disagree. Keryx only
publishes roles located in the United States or explicitly marked remote within the United States.

## Link safety

Every published application URL passes Keryx's deterministic cleaner before it becomes clickable:

- HTTPS is enforced; fragments, tracking parameters, and duplicate query keys are removed.
- Credentials, IP-literal/private-style destinations, nonstandard ports, parser-confusing escapes,
  executable downloads, URL shorteners, generic forms, and file-sharing links are rejected.
- The updater can contact only the fixed GitHub feeds and recognized Greenhouse, Ashby, Lever, and
  Workday API hosts; automatic redirects are disabled.
- Each Apply link displays its destination host and whether it was checked through a direct ATS,
  corroborated by multiple sources, or recognized as a structured recruiting-platform URL.
- A custom-domain link reported by only one community source is withheld until another source or
  a direct ATS observation corroborates it; the role remains searchable without a clickable URL.
- Rejected URLs are omitted from the databases. A non-clickable fingerprint and rejection reason
  are retained in [`data/quarantine.json`](data/quarantine.json) for auditing.

These controls reduce phishing, tracking, parser-confusion, and SSRF risk, but no public index can
guarantee an employer or posting is legitimate. Confirm the company and destination before sharing
personal information. Never pay an application fee or provide passwords, banking credentials, or
government identity documents solely because a listing appears here.

## Automation

The update workflow runs every 15 minutes and commits only when the database actually changes.
Temporary source failures do not remove jobs. A listing must disappear from every successfully
checked source for two consecutive runs before Keryx closes it.

Keryx does not accept applications, store applicant information, or use an AI model. It is a public,
deterministic index of public job postings.
