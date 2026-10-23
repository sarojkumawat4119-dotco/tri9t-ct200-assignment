"""End-to-end smoke demonstration against a running local API."""
import json, sys, time
from pathlib import Path
import requests
BASE=sys.argv[1] if len(sys.argv)>1 else 'http://127.0.0.1:8000'
ROOT=Path(__file__).resolve().parents[1]
def call(method,path,**kwargs):
    r=requests.request(method,BASE+path,timeout=60,**kwargs)
    if not r.ok: raise RuntimeError(f'{method} {path} -> {r.status_code}: {r.text}')
    return r.json()
call('POST','/ingest',json={'pdf_path':str(ROOT/'data/ct200_manual.pdf')})
search=call('GET','/nodes/search',params={'q':'Battery Life','version':1})['results'][0]
search2=call('GET','/nodes/search',params={'q':'Cuff Inflation Sequence','version':1})['results'][0]
selection=call('POST','/selections',json={'name':'Demo selection from v1','node_ids':[search['id'],search2['id']]})
gen=call('POST','/generate',json={'selection_id':selection['selection_id']})
call('POST','/ingest',json={'pdf_path':str(ROOT/'data/ct200_manual_v2.pdf')})
retrieved=call('GET',f"/generations/{gen['generation_id']}")
assert retrieved['staleness']['stale'], 'Expected v1 generation to be stale after v2 re-ingestion'
print(json.dumps({'selection_id':selection['selection_id'],'generation_id':gen['generation_id'],'case_count':len(gen['test_cases']),'provider':gen['provider'],'staleness':retrieved['staleness']},indent=2))
