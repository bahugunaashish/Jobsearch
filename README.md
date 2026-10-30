# IIT and NIT Faculty Vacancy Monitor

A Streamlit dashboard and command-line email monitor for potential Assistant Professor notices found by visiting institute sites and following recruitment links. No Google News RSS is used.

## Run the dashboard

Requires Python 3.9 or newer. In a terminal:

```bash
pip install -r requirements.txt
streamlit run app.py
```

Choose institutes and click Search. Download the results as CSV. The app does not run a background job or send daily emails by itself.

## Daily email

Run `python iit_nit_vacancies.py --dry-run` to test without sending mail. To send a daily digest configure SMTP_HOST, SMTP_PORT, SMTP_USERNAME, SMTP_PASSWORD, and EMAIL_TO as environment variables accessible to the scheduled process. Gmail typically uses smtp.gmail.com, port 587, and an app password. Never commit credentials. Run `python iit_nit_vacancies.py` using Windows Task Scheduler or cron each day. The process must have a persistent writable directory for `faculty_seen.json`; it sends only new matches plus coverage issues. The first run reports all matches. Use `--all` to resend all matches. `--sites sites.json` overrides the institution list with a JSON name-to-homepage mapping.

## Coverage and limitations

These are potential leads, not verified open vacancies. Check the official notice for deadlines and eligibility. The crawler follows selected recruitment-related links, extracts text from HTML and the first 40 pages of PDF notices, respects robots.txt, and limits requests. It cannot extract scanned PDFs, dynamically rendered content, links outside the institute domain, or notices not reached by the crawler. Websites and seed addresses can change; consult the coverage/issue report and edit the SITES dictionary as needed. The seed list and live website behavior have not been verified in this environment. The email search can take considerable time and requires a machine that remains available at the scheduled time.
