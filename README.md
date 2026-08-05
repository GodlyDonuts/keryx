# Keryx

Keryx is a continuously updated database of **United States internships and new-graduate roles**.
GitHub Actions collects public listings, verifies them against direct applicant-tracking-system
feeds when possible, removes duplicates, and rebuilds the Markdown databases automatically.

## Opportunity databases

<!-- COUNTS:START -->
| Recruiting cycle | Open roles |
|---|---:|
| [Summer 2027 US Internships](internships/summer-2027.md) | 336 |
| [Fall 2026 US Internships](internships/fall-2026.md) | 439 |
| [Spring 2027 US Internships](internships/spring-2027.md) | 29 |
| [Winter 2027 US Internships](internships/winter-2027.md) | 8 |
| [US Internships — Cycle Not Stated](internships/unscheduled.md) | 396 |
| [2027 US New-Graduate Roles](new-grad/2027.md) | 586 |
| [2026 US New-Graduate Roles](new-grad/2026.md) | 32 |
| [US New-Graduate Roles — Cycle Not Stated](new-grad/unscheduled.md) | 1758 |
<!-- COUNTS:END -->

The Markdown files are the product: open them directly on GitHub, search them, bookmark them, or
consume the canonical [`data/jobs.json`](data/jobs.json) file from another program.

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
