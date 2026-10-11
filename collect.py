"""Conservative JSON-LD event collector for official cultural venue pages."""
import json, re, html, datetime, urllib.request
from pathlib import Path
from zoneinfo import ZoneInfo

ROOT=Path(__file__).parent
SOURCES=[
 ('Barbican','https://www.barbican.org.uk/whats-on'),
 ('Southbank Centre','https://www.southbankcentre.co.uk/whats-on'),
 ('V&A','https://www.vam.ac.uk/whatson'),
 ('National Theatre','https://www.nationaltheatre.org.uk/whats-on/'),
 ('Young Vic','https://www.youngvic.org/whats-on'),
 ('Tate','https://www.tate.org.uk/whats-on'),
 ('Royal Academy','https://www.royalacademy.org.uk/exhibitions-and-events'),
 ('Science Museum','https://www.sciencemuseum.org.uk/see-and-do'),
 ('Natural History Museum','https://www.nhm.ac.uk/visit/exhibitions.html'),
 ('British Museum','https://www.britishmuseum.org/exhibitions-events'),
 ('Whitechapel Gallery','https://www.whitechapelgallery.org/exhibitions/'),
 ('Sadlers Wells','https://www.sadlerswells.com/whats-on/'),
]
KEYWORDS=('immersive','installation','contemporary','modern art','theatre','opera','ballet','classical','family','children','exhibition','performance','digital art')
def extract_objects(v):
 if isinstance(v,list):
  for x in v: yield from extract_objects(x)
 elif isinstance(v,dict):
  if '@graph' in v: yield from extract_objects(v['@graph'])
  typ=v.get('@type',[]); typ=[typ] if isinstance(typ,str) else typ
  if any(t in ('Event','ExhibitionEvent','TheaterEvent','MusicEvent','DanceEvent','ChildrensEvent','VisualArtsEvent') for t in typ): yield v

def datepart(x):
 if not x:return None
 m=re.match(r'\d{4}-\d{2}-\d{2}',str(x));return m.group(0) if m else None

def textval(x):return re.sub(r'<[^>]*>','',html.unescape(str(x or ''))).strip()

def parse_event(e,venue):
 title=textval(e.get('name'));start=datepart(e.get('startDate'));end=datepart(e.get('endDate')) or start
 url=e.get('url');url=url.get('@id') if isinstance(url,dict) else url
 if not title or not start or not isinstance(url,str) or not url.startswith('https://'):return None
 if end<datetime.date.today().isoformat():return None
 desc=textval(e.get('description'))[:220];low=(title+' '+desc).lower()
 category='family' if any(w in low for w in ('family','children','kids')) else 'performance' if any(w in low for w in ('theatre','opera','ballet','concert','performance','music')) else 'art'
 img=None # no automatic third-party image reuse without permissions
 return dict(title=title,venue=venue,category=category,family_friendly=category=='family',start_date=start,end_date=end,opening_hours='',verified_time=False,description=desc,url=url,image_url=img,score=55+min(35,sum(8 for w in KEYWORDS if w in low)))

def main():
 now=datetime.datetime.now(ZoneInfo('Europe/London'));cutoff=(now.date()+datetime.timedelta(days=7)).isoformat();out=[];errors=[]
 for venue,url in SOURCES:
  try:
   req=urllib.request.Request(url,headers={'User-Agent':'LondonCultureRadar/0.1 (+personal cultural discovery; respectful requests)'})
   with urllib.request.urlopen(req,timeout=15) as r: page=r.read(2_000_000).decode('utf-8','replace')
   blocks=re.findall(r'<script[^>]+type=["\']application/ld\+json["\'][^>]*>(.*?)</script>',page,re.I|re.S)
   for block in blocks:
    try: objs=list(extract_objects(json.loads(block)))
    except (ValueError,TypeError):continue
    for e in objs:
     rec=parse_event(e,venue)
     if rec and rec['start_date']<=cutoff:out.append(rec)
  except Exception as ex:errors.append(f'{venue}: {type(ex).__name__}: {ex}')
 seen=set();unique=[]
 for e in out:
  k=(e['title'].casefold(),e['venue'],e['start_date'])
  if k not in seen:seen.add(k);unique.append(e)
 # Keep previous results when all sources fail; never overwrite with empty data silently.
 if not unique:
  old=json.loads((ROOT/'events.json').read_text())
  if old.get('events'):
   print('No fresh records. Keeping prior dataset. Errors:',errors)
   raise SystemExit(1)
 data={'updated_at':now.isoformat(timespec='minutes'),'events':unique,'source_errors':errors,'sources_checked':len(SOURCES)}
 (ROOT/'events.json').write_text(json.dumps(data,ensure_ascii=False,indent=2)+'\n')
 print(f'Collected {len(unique)} events; {len(errors)} source errors')
 if errors:print('\n'.join(errors))
 if not unique:raise SystemExit('No events extracted; pipeline needs source-specific adapters. Do not publish as populated.')
if __name__=='__main__':main()
