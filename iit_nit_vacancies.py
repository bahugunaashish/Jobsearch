#!/usr/bin/env python3
"""Daily IIT/NIT faculty recruitment monitor. Run --help for setup.

Install: pip install requests beautifulsoup4 pypdf
Searches institution sites directly, including linked PDF notices. No Google RSS.
"""
import argparse, csv, hashlib, io, json, os, re, smtplib, ssl, sys, time
from collections import deque
from datetime import date, datetime
from email.message import EmailMessage
from pathlib import Path
from urllib.parse import urljoin, urlparse, urldefrag
from urllib.robotparser import RobotFileParser

import requests
from bs4 import BeautifulSoup
from pypdf import PdfReader

# Seeds are a starting inventory. Domains and sites can change; failures are
# reported in the digest. You can edit this dictionary or provide --sites JSON.
SITES = {
'IIT Bhilai':'https://www.iitbhilai.ac.in/', 'IIT Bhubaneswar':'https://www.iitbbs.ac.in/',
'IIT Bombay':'https://www.iitb.ac.in/', 'IIT Delhi':'https://home.iitd.ac.in/',
'IIT Dharwad':'https://www.iitdh.ac.in/', 'IIT Gandhinagar':'https://iitgn.ac.in/',
'IIT Goa':'https://iitgoa.ac.in/', 'IIT Guwahati':'https://www.iitg.ac.in/',
'IIT Hyderabad':'https://iith.ac.in/', 'IIT Indore':'https://www.iiti.ac.in/',
'IIT Jammu':'https://www.iitjammu.ac.in/', 'IIT Jodhpur':'https://iitj.ac.in/',
'IIT Kanpur':'https://www.iitk.ac.in/', 'IIT Kharagpur':'https://www.iitkgp.ac.in/',
'IIT Madras':'https://www.iitm.ac.in/', 'IIT Mandi':'https://www.iitmandi.ac.in/',
'IIT Palakkad':'https://iitpkd.ac.in/', 'IIT Patna':'https://www.iitp.ac.in/',
'IIT Roorkee':'https://www.iitr.ac.in/', 'IIT Ropar':'https://www.iitrpr.ac.in/',
'IIT Tirupati':'https://www.iittp.ac.in/', 'IIT (BHU) Varanasi':'https://www.iitbhu.ac.in/',
'IIT (ISM) Dhanbad':'https://www.iitism.ac.in/',
'NIT Agartala':'https://www.nita.ac.in/', 'NIT Andhra Pradesh':'https://www.nitandhra.ac.in/',
'NIT Arunachal Pradesh':'https://nitap.ac.in/', 'NIT Calicut':'https://nitc.ac.in/',
'NIT Delhi':'https://nitdelhi.ac.in/', 'NIT Durgapur':'https://nitdgp.ac.in/',
'NIT Goa':'https://www.nitgoa.ac.in/', 'NIT Hamirpur':'https://nith.ac.in/',
'NIT Jamshedpur':'https://www.nitjsr.ac.in/', 'NIT Karnataka':'https://www.nitk.ac.in/',
'NIT Kurukshetra':'https://nitkkr.ac.in/', 'NIT Manipur':'https://www.nitmanipur.ac.in/',
'NIT Meghalaya':'https://www.nitm.ac.in/', 'NIT Mizoram':'https://www.nitmz.ac.in/',
'NIT Nagaland':'https://nitnagaland.ac.in/', 'NIT Patna':'https://www.nitp.ac.in/',
'NIT Puducherry':'https://nitpy.ac.in/', 'NIT Raipur':'https://www.nitrr.ac.in/',
'NIT Rourkela':'https://www.nitrkl.ac.in/', 'NIT Sikkim':'https://www.nitsikkim.ac.in/',
'NIT Silchar':'https://www.nits.ac.in/', 'NIT Srinagar':'https://www.nitsri.ac.in/',
'NIT Tiruchirappalli':'https://www.nitt.edu/', 'NIT Uttarakhand':'https://nituk.ac.in/',
'NIT Warangal':'https://www.nitw.ac.in/', 'MNIT Jaipur':'https://www.mnit.ac.in/',
'MNNIT Allahabad':'https://www.mnnit.ac.in/', 'NIT Nagpur (VNIT)':'https://vnit.ac.in/',
'NIT Bhopal (MANIT)':'https://www.manit.ac.in/', 'NIT Jalandhar':'https://www.nitj.ac.in/',
'NIT Surat (SVNIT)':'https://www.svnit.ac.in/',
}
ROLE = re.compile(r'\bass(?:istan)?t\.?\s*(?:professor|prof\.?)(?:s)?\b', re.I)
RECRUIT = re.compile(r'recruit|vacanc|career|faculty|advertis|employment|jobs?|opening|appointment|notices?|opportunities|positions?|notification', re.I)
DATE = re.compile(r'\b(?:last\s+date|closing\s+date|deadline|apply\s+by|applications?\s+(?:must\s+be\s+)?(?:received|submitted)\s+(?:by|before)|last\s+date\s+of\s+submission)[^\n.]{0,100}', re.I)
HEADERS = {'User-Agent':'FacultyVacancyMonitor/1.0 (academic recruitment search)'}
BASE = Path(__file__).resolve().parent

def clean(text): return re.sub(r'\s+', ' ', text).strip()
def fingerprint(s): return hashlib.sha256(s.encode('utf-8')).hexdigest()
def same_site(a,b):
    # Allow subdomains of the starting institute host, including www variants.
    a=urlparse(a).hostname or ''; b=urlparse(b).hostname or ''
    a=a.removeprefix('www.'); b=b.removeprefix('www.')
    return a==b or a.endswith('.'+b) or b.endswith('.'+a)

def fetch(session, url, max_bytes=12_000_000):
    with session.get(url, timeout=25, stream=True, allow_redirects=True) as r:
        r.raise_for_status()
        if not same_site(url, r.url): raise ValueError('redirected outside institute domain')
        chunks=[]; total=0
        for chunk in r.iter_content(65536):
            total += len(chunk)
            if total > max_bytes: raise ValueError('file exceeds size limit')
            chunks.append(chunk)
        return r.url, r.headers.get('Content-Type','').lower(), b''.join(chunks)

def crawl(name, seed, limit, delay):
    session=requests.Session(); session.headers.update(HEADERS)
    queue=deque([(seed,0)]); visited=set(); hits=[]; errors=[]; robots={}
    while queue and len(visited)<limit:
        url, depth=queue.popleft(); url=urldefrag(url)[0]
        if url in visited or not same_site(seed,url): continue
        visited.add(url)
        parsed=urlparse(url); origin=f'{parsed.scheme}://{parsed.netloc}'
        if origin not in robots:
            rp=RobotFileParser(); rp.set_url(origin+'/robots.txt')
            try:
                rr=session.get(origin+'/robots.txt',timeout=15,headers=HEADERS)
                if rr.status_code in (401,403): rp.parse(['User-agent: *','Disallow: /'])
                elif rr.status_code == 404: rp.parse([])
                else:
                    rr.raise_for_status(); rp.parse(rr.text.splitlines())
                robots[origin]=rp
            except requests.RequestException as e:
                robots[origin]=None; errors.append(f'{name}: robots.txt unavailable at {origin}: {e}')
        if robots[origin] is None or not robots[origin].can_fetch(HEADERS['User-Agent'],url):
            continue
        try:
            final, content_type, data=fetch(session,url)
            if 'application/pdf' in content_type or url.lower().split('?')[0].endswith('.pdf'):
                reader=PdfReader(io.BytesIO(data))
                text='\n'.join((p.extract_text() or '') for p in reader.pages[:40])
                title=url.rsplit('/',1)[-1]
                if ROLE.search(text):
                    match=DATE.search(text)
                    hits.append(dict(institute=name,title=title,url=final,deadline=clean(match.group()) if match else 'Not identified; check notice', evidence='PDF text contains Assistant Professor'))
            elif 'html' in content_type or data.lstrip().lower().startswith((b'<!doctype html',b'<html')):
                soup=BeautifulSoup(data,'html.parser')
                for x in soup(['script','style','nav','footer']): x.decompose()
                text=soup.get_text(' ',strip=True)
                # Match individual notice links so one generic page does not hide
                # distinct advertisements. Include target PDFs in crawl queue.
                for a in soup.find_all('a',href=True):
                    label=clean(a.get_text(' ',strip=True)); target=urldefrag(urljoin(final,a['href']))[0]
                    if not target.startswith(('http://','https://')) or not same_site(seed,target): continue
                    if ROLE.search(label):
                        parent=clean(a.parent.get_text(' ',strip=True)) if a.parent else label
                        dm=DATE.search(parent)
                        hits.append(dict(institute=name,title=label[:300],url=target,deadline=clean(dm.group()) if dm else 'Not identified; check notice',evidence='Notice link mentions Assistant Professor'))
                    if depth<3 and (RECRUIT.search(label+' '+target) or ROLE.search(label+' '+target)):
                        queue.append((target,depth+1))
                if ROLE.search(text) and (depth>0 or RECRUIT.search(text)):
                    dm=DATE.search(text)
                    hits.append(dict(institute=name,title=clean(soup.title.get_text())[:200] if soup.title else 'Recruitment page',url=final,deadline=clean(dm.group()) if dm else 'Not identified; check notice',evidence='Page mentions Assistant Professor'))
        except Exception as e:
            errors.append(f'{name}: {url}: {type(e).__name__}: {str(e)[:180]}')
        time.sleep(delay)
    if queue: errors.append(f'{name}: page limit reached; site coverage incomplete')
    return hits,errors,len(visited)

def mail(subject, body):
    user=os.environ['SMTP_USERNAME']; password=os.environ['SMTP_PASSWORD']; dest=os.environ['EMAIL_TO']
    msg=EmailMessage(); msg['From']=os.environ.get('EMAIL_FROM',user); msg['To']=dest; msg['Subject']=subject; msg.set_content(body)
    host=os.environ.get('SMTP_HOST','smtp.gmail.com'); port=int(os.environ.get('SMTP_PORT','587'))
    if port==465:
        with smtplib.SMTP_SSL(host,port,timeout=30,context=ssl.create_default_context()) as s: s.login(user,password); s.send_message(msg)
    else:
        with smtplib.SMTP(host,port,timeout=30) as s: s.ehlo(); s.starttls(context=ssl.create_default_context()); s.login(user,password); s.send_message(msg)

def main():
    p=argparse.ArgumentParser(description=__doc__,formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument('--sites',help='JSON mapping institute names to official home URLs; overrides built-in list')
    p.add_argument('--limit',type=int,default=35,help='Maximum pages per institute (default 35)')
    p.add_argument('--delay',type=float,default=0.5,help='Seconds between requests (default 0.5)')
    p.add_argument('--dry-run',action='store_true',help='Save CSV and print results without sending email or updating seen state')
    p.add_argument('--all',action='store_true',help='Email all matches, including previously reported ones')
    args=p.parse_args()
    if args.limit<1 or args.delay<0: p.error('limit must be positive and delay nonnegative')
    sites=json.loads(Path(args.sites).read_text(encoding='utf-8')) if args.sites else SITES
    if not isinstance(sites,dict) or not sites: p.error('sites must be a nonempty JSON object')
    state=BASE/'faculty_seen.json'; seen=set(json.loads(state.read_text(encoding='utf-8'))) if state.exists() else set()
    matches={}; errors=[]; coverage=[]
    for name, url in sites.items():
        print('Checking',name,url,flush=True)
        found,problems,count=crawl(name,url,args.limit,args.delay); errors.extend(problems); coverage.append(f'{name}: {count} pages attempted; {len(problems)} issue(s)')
        for hit in found: matches[(hit['institute'],hit['url'])]=hit
    rows=list(matches.values()); new=[h for h in rows if args.all or fingerprint(h['institute']+'|'+h['url']+'|'+h['title']+'|'+h['deadline']) not in seen]
    with (BASE/'faculty_results.csv').open('w',newline='',encoding='utf-8-sig') as f:
        w=csv.DictWriter(f,fieldnames=['institute','title','url','deadline','evidence']); w.writeheader(); w.writerows(rows)
    lines=[f'{len(new)} new potential matches; {len(rows)} total matches.', 'These are leads, not verified open positions. Confirm post, eligibility and deadline in the official notice. Dates may be missing or unrelated.', '']
    for h in new: lines += [f"{h['institute']}: {h['title']}",f"URL: {h['url']}",f"Possible deadline: {h['deadline']}",f"Evidence: {h['evidence']}",'']
    lines += ['COVERAGE',*coverage,'','ERRORS / INCOMPLETE COVERAGE',*(errors or ['None recorded.'])]
    body='\n'.join(lines)
    if args.dry_run: print(body); return
    try: mail(f'IIT/NIT faculty monitor: {len(new)} new potential matches',body)
    except Exception as e: print(f'Email failed; state was not updated: {e}',file=sys.stderr); sys.exit(1)
    seen.update(fingerprint(h['institute']+'|'+h['url']+'|'+h['title']+'|'+h['deadline']) for h in new)
    tmp=state.with_suffix('.tmp'); tmp.write_text(json.dumps(sorted(seen),indent=2),encoding='utf-8'); tmp.replace(state)
    print(f'Email sent; {len(rows)} matches saved to faculty_results.csv')
if __name__=='__main__': main()
