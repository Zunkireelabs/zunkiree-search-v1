# Admizz catalog data request

**For:** whoever owns the Admizz database / website data (Zunkiree built admizzeducation.com).
**Why:** the education counselor chatbot needs exact, current university and course data. Today we read it from the public website pages, which is fragile and incomplete.

## What we have from the website (2026-10-27)
61 UK universities, 1,981 courses. Gaps the website itself has:
- **729 courses show only "from £X"**, a minimum. We need the exact fee per course.
- **220 courses show a multi-year total** with no yearly split.
- **Coventry University and Liverpool Hope University** show "Course list coming soon".
- **Surrey and some others** show "Ask a counsellor" instead of a fee.
- Only the UK is covered. We need the same for Australia, Canada, USA, Germany (and any other destination Admizz sells).

## What we are asking for
A data export (CSV, JSON or a read-only database view), one row per course, with the fields below. "Required" means the chatbot cannot show a card without it.

### Universities (one row each)
| Field | Required | Notes |
|---|---|---|
| `university_id` / slug | yes | stable id |
| `name` | yes | |
| `country` | yes | |
| `city` / campus locations | yes | |
| `website` | no | |
| `intake months` | yes | |
| `scholarships` (name, amount, who qualifies) | no | |
| `last_verified` date | yes | when Admizz last checked this record |

### Courses (one row each)
| Field | Required | Notes |
|---|---|---|
| `course_id` | yes | stable id |
| `university_id` | yes | |
| `name` | yes | |
| `level` | yes | foundation / bachelor / master / PhD |
| `field of study` | yes | e.g. Computer Science, Business |
| `duration` | yes | months |
| `tuition amount` | yes | exact figure, not "from" |
| `tuition currency` | yes | |
| `tuition basis` | yes | **per year** or **total for the whole course** |
| `intake months` | yes | per course |
| `IELTS minimum` | yes | per course or per level |
| `academic minimum` | no | percentage or GPA, and which qualification |
| `entry route` | no | for pathway courses: foundation / year zero / pre-master |
| `last_verified` date | yes | |

### Country facts (one row per destination)
Living cost range, post-study work visa length, work rights during study, funds required for the visa, and the date each was checked.

## Questions for the data owner
1. Is this data public, or may we use it for the chatbot? The course finder and university pages are currently marked `noindex`.
2. Who confirms the numbers are accurate, and how often are they updated?
3. Can we get a feed or a read-only view so the chatbot stays current without scraping?
4. Which currency should students see: the university's (GBP) or NPR?

## What we do with it
Load it as the chatbot's catalog, shown to students as the source of fees, intakes and entry requirements. Nothing is shown to students as confirmed until Admizz confirms it.
