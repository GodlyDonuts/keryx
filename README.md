# Keryx

Keryx is a continuously updated database of **United States internships and new-graduate roles**.
GitHub Actions collects public listings, verifies them against direct applicant-tracking-system
feeds when possible, removes duplicates, and rebuilds the Markdown databases automatically.

## Opportunity databases

<!-- COUNTS:START -->
| Recruiting cycle | Open roles |
|---|---:|
| [Summer 2027 US Internships](internships/summer-2027.md) | 187 |
| [Fall 2026 US Internships](internships/fall-2026.md) | 304 |
| [Spring 2027 US Internships](internships/spring-2027.md) | 15 |
| [Winter 2027 US Internships](internships/winter-2027.md) | 6 |
| [US Internships — Cycle Not Stated](internships/unscheduled.md) | 320 |
| [2027 US New-Graduate Roles](new-grad/2027.md) | 685 |
| [2026 US New-Graduate Roles](new-grad/2026.md) | 30 |
| [US New-Graduate Roles — Cycle Not Stated](new-grad/unscheduled.md) | 1719 |
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

Community repositories are discovery sources. Every row links to the employer's application page,
and direct ATS observations take precedence when duplicate records disagree. Keryx only publishes
roles located in the United States or explicitly marked remote within the United States.

## Automation

The update workflow runs every 15 minutes and commits only when the database actually changes.
Temporary source failures do not remove jobs. A listing must disappear from every successfully
checked source for two consecutive runs before Keryx closes it.

Keryx does not accept applications, store applicant information, or use an AI model. It is a public,
deterministic index of public job postings.
