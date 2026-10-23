from fastapi import FastAPI, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from sqlalchemy import select
from pathlib import Path
from datetime import datetime, timezone
import hashlib, difflib, json, re, uuid
from app.db import Base, engine, get_db
from app.models import Document, DocumentVersion, Node, Selection, SelectionItem
from app.parser import parse_pdf, sha256, normalize
from app.schemas import IngestRequest, SelectionRequest, GenerateRequest
from app.generation import call_llm, save_generation, read_store

Base.metadata.create_all(bind=engine)
app=FastAPI(title='Tri9T CT-200 Traceable QA API',version='1.0.0',description='Versioned CT-200 document extraction, selection, QA generation and staleness detection.')
def utcnow(): return datetime.now(timezone.utc).isoformat()
def version_num(db, version):
    if version is not None: return version
    v=db.scalar(select(DocumentVersion).order_by(DocumentVersion.version_number.desc()).limit(1))
    if not v: raise HTTPException(404,'No document version ingested yet')
    return v.version_number
def get_version(db, version=None):
    num=version_num(db,version)
    v=db.scalar(select(DocumentVersion).where(DocumentVersion.version_number==num))
    if not v: raise HTTPException(404,f'Document version {num} not found')
    return v
def node_dict(n, include_children=False):
    d={'id':n.id,'logical_id':n.logical_id,'version_id':n.version_id,'heading':n.heading,'number':n.number,'level':n.level,'body_text':n.body_text,'content_hash':n.content_hash,'page_start':n.page_start,'page_end':n.page_end,'node_type':n.node_type,'parent_id':n.parent_id}
    if include_children: d['children']=[node_dict(c,True) for c in n.children]
    return d
@app.get('/health')
def health(): return {'status':'ok'}
@app.post('/ingest')
def ingest(req: IngestRequest, db: Session=Depends(get_db)):
    path=Path(req.pdf_path)
    if not path.exists(): raise HTTPException(400,f'PDF not found: {path}')
    raw=path.read_bytes(); source_hash=hashlib.sha256(raw).hexdigest()
    doc=db.scalar(select(Document).where(Document.name=='CT-200 Manual'))
    if doc is None: doc=Document(name='CT-200 Manual'); db.add(doc); db.flush()
    existing=db.scalar(select(DocumentVersion).where(DocumentVersion.document_id==doc.id,DocumentVersion.source_sha256==source_hash))
    if existing: return {'message':'Identical PDF already ingested; no duplicate version created.','version':existing.version_number,'node_count':len(existing.nodes)}
    version_no=(db.scalar(select(DocumentVersion.version_number).where(DocumentVersion.document_id==doc.id).order_by(DocumentVersion.version_number.desc()).limit(1)) or 0)+1
    parsed=parse_pdf(path)
    old_version=db.scalar(select(DocumentVersion).where(DocumentVersion.document_id==doc.id).order_by(DocumentVersion.version_number.desc()).limit(1))
    old_nodes=old_version.nodes if old_version else []
    # Match key includes section number + normalized heading + ancestor path. Hash is deliberately not part of identity so edits preserve logical IDs.
    def path_key(raw_node, parsed_nodes):
        chain=[]; i=raw_node.get('parent_index')
        while i is not None:
            p=parsed_nodes[i]; chain.append((p['number'],normalize(p['heading']).casefold())); i=p['parent_index']
        return tuple(reversed(chain))+((raw_node['number'],normalize(raw_node['heading']).casefold()),)
    old_by_key={}
    if old_version:
        byid={n.id:n for n in old_nodes}
        for n in old_nodes:
            chain=[]; p=n.parent
            while p is not None: chain.append((p.number,normalize(p.heading).casefold())); p=p.parent
            key=tuple(reversed(chain))+((n.number,normalize(n.heading).casefold()),)
            old_by_key.setdefault(key,[]).append(n)
    version=DocumentVersion(document_id=doc.id,version_number=version_no,source_filename=path.name,source_sha256=source_hash,created_at=utcnow()); db.add(version); db.flush()
    created=[]
    for i,p in enumerate(parsed):
        key=path_key(p,parsed)
        candidates=old_by_key.get(key,[])
        old=candidates.pop(0) if candidates else None
        logical_id=old.logical_id if old else str(uuid.uuid4())
        parent=created[p['parent_index']] if p['parent_index'] is not None else None
        n=Node(logical_id=logical_id,version_id=version.id,parent_id=parent.id if parent else None,heading=p['heading'],number=p['number'],level=p['level'],body_text=p['body_text'],content_hash=sha256(p['heading']+'\n'+p['body_text']),page_start=p['page_start'],page_end=p['page_end'],node_type=p['node_type'])
        db.add(n); db.flush(); created.append(n)
    db.commit()
    changed=sum(1 for n in created if any(o.logical_id==n.logical_id and o.content_hash!=n.content_hash for o in old_nodes))
    return {'message':'Ingestion complete','document_id':doc.id,'version':version_no,'source_filename':path.name,'node_count':len(created),'matched_to_previous_version':len(created)-sum(1 for n in created if n.logical_id not in {o.logical_id for o in old_nodes}),'changed_matched_nodes':changed,'note':'OCR is a fallback for pages with no usable text layer; verify OCR pages visually.'}
@app.get('/versions')
def versions(db:Session=Depends(get_db)):
    return [{'version':v.version_number,'filename':v.source_filename,'sha256':v.source_sha256,'created_at':v.created_at,'node_count':len(v.nodes)} for v in db.scalars(select(DocumentVersion).order_by(DocumentVersion.version_number)).all()]
@app.get('/sections')
def sections(version:int|None=None, db:Session=Depends(get_db)):
    v=get_version(db,version)
    return {'version':v.version_number,'sections':[node_dict(n) for n in v.nodes if n.level==1 and n.node_type=='section']}
@app.get('/nodes/search')
def search(q:str=Query(min_length=1), version:int|None=None, db:Session=Depends(get_db)):
    v=get_version(db,version); needle=f'%{q}%'
    nodes=db.scalars(select(Node).where(Node.version_id==v.id, (Node.heading.ilike(needle)) | (Node.body_text.ilike(needle))).order_by(Node.id)).all()
    return {'version':v.version_number,'query':q,'results':[node_dict(n) for n in nodes]}
@app.get('/nodes/{node_id}')
def get_node(node_id:int, db:Session=Depends(get_db)):
    n=db.get(Node,node_id)
    if not n: raise HTTPException(404,'Node not found')
    return node_dict(n,True)
@app.get('/nodes/{node_id}/changes')
def changes(node_id:int, db:Session=Depends(get_db)):
    n=db.get(Node,node_id)
    if not n: raise HTTPException(404,'Node not found')
    version=db.get(DocumentVersion,n.version_id)
    all_versions=db.scalars(select(DocumentVersion).where(DocumentVersion.document_id==version.document_id).order_by(DocumentVersion.version_number)).all()
    latest=all_versions[-1]
    current=db.scalar(select(Node).where(Node.version_id==latest.id,Node.logical_id==n.logical_id))
    if current is None: return {'logical_id':n.logical_id,'source_version':version.version_number,'latest_version':latest.version_number,'changed':True,'status':'removed_or_unmatched','summary':'No corresponding logical node found in latest version.'}
    changed=n.content_hash!=current.content_hash
    a=n.body_text.split(); b=current.body_text.split()
    diff=list(difflib.unified_diff(a,b,fromfile=f'v{version.version_number}',tofile=f'v{latest.version_number}',n=3)) if changed else []
    return {'logical_id':n.logical_id,'source_version':version.version_number,'latest_version':latest.version_number,'changed':changed,'status':'changed' if changed else 'unchanged','source_hash':n.content_hash,'latest_hash':current.content_hash,'source_heading':n.heading,'latest_heading':current.heading,'diff_summary':{'removed_tokens':sum(1 for x in difflib.SequenceMatcher(a=a,b=b).get_opcodes() if x[0] in ('delete','replace') for _ in a[x[1]:x[2]]),'added_tokens':sum(1 for x in difflib.SequenceMatcher(a=a,b=b).get_opcodes() if x[0] in ('insert','replace') for _ in b[x[3]:x[4]]),'preview':' '.join(diff)[:1200]}}
@app.post('/selections')
def create_selection(req:SelectionRequest, db:Session=Depends(get_db)):
    nodes=[]
    for nid in req.node_ids:
        n=db.get(Node,nid)
        if not n: raise HTTPException(404,f'Node {nid} not found')
        nodes.append(n)
    # Enforce one version per selection; otherwise selected text would mix baselines.
    if len({n.version_id for n in nodes})!=1: raise HTTPException(400,'All selected nodes must belong to the same document version.')
    s=Selection(name=req.name,created_at=utcnow()); db.add(s); db.flush()
    for n in nodes: db.add(SelectionItem(selection_id=s.id,node_id=n.id,version_id=n.version_id,logical_id=n.logical_id,content_hash=n.content_hash,snapshot_heading=n.heading,snapshot_text=(n.heading+'\n'+n.body_text).strip()))
    db.commit(); return {'selection_id':s.id,'name':s.name,'version_id':nodes[0].version_id,'node_ids':req.node_ids,'pinned':True}
@app.get('/selections/{selection_id}')
def get_selection(selection_id:int, db:Session=Depends(get_db)):
    s=db.get(Selection,selection_id)
    if not s: raise HTTPException(404,'Selection not found')
    return {'selection_id':s.id,'name':s.name,'created_at':s.created_at,'items':[{'node_id':i.node_id,'version_id':i.version_id,'logical_id':i.logical_id,'content_hash':i.content_hash,'heading':i.snapshot_heading,'text':i.snapshot_text} for i in s.items]}
@app.post('/generate')
def generate(req:GenerateRequest, db:Session=Depends(get_db)):
    s=db.get(Selection,req.selection_id)
    if not s: raise HTTPException(404,'Selection not found')
    source_nodes=[]; chunks=[]
    for i in s.items:
        v=db.get(DocumentVersion,i.version_id)
        source_nodes.append({'node_id':i.node_id,'logical_id':i.logical_id,'version_id':i.version_id,'version_number':v.version_number,'heading':i.snapshot_heading,'content_hash':i.content_hash,'text':i.snapshot_text})
        chunks.append(f"[Node {i.node_id} | logical {i.logical_id} | version {v.version_number} | hash {i.content_hash}]\n{i.snapshot_text}")
    try: payload=call_llm('\n\n'.join(chunks),[i.node_id for i in s.items])
    except RuntimeError as e: raise HTTPException(502,str(e))
    record=save_generation(s.id,s.name,source_nodes,payload)
    return {'generation_id':record['generation_id'],'selection_id':s.id,'case_count':len(record['test_cases']),'provider':record['provider'],'test_cases':record['test_cases'],'source_version_ids':[n['version_id'] for n in source_nodes]}
def generation_status(g):
    statuses=[]
    with next(get_db()) as db:
        for src in g['source_nodes']:
            v=db.get(DocumentVersion,src['version_id'])
            latest=db.scalar(select(DocumentVersion).where(DocumentVersion.document_id==v.document_id).order_by(DocumentVersion.version_number.desc()).limit(1)) if v else None
            current=db.scalar(select(Node).where(Node.version_id==latest.id,Node.logical_id==src['logical_id'])) if latest else None
            statuses.append({'logical_id':src['logical_id'],'source_version':src['version_number'],'latest_version':latest.version_number if latest else None,'changed':(current is None or current.content_hash!=src['content_hash']),'status':'removed_or_unmatched' if current is None else ('changed' if current.content_hash!=src['content_hash'] else 'unchanged'),'source_hash':src['content_hash'],'current_hash':current.content_hash if current else None})
    changed=[x for x in statuses if x['changed']]
    return {'stale':bool(changed),'staleness':'stale' if changed else 'current','changed_sources':changed,'source_statuses':statuses,'limitation':'Hash-based change detection treats any normalized text change alike; it flags potential staleness, not clinical impact or automatic invalidity.'}
@app.get('/generations')
def list_generations(selection_id:int|None=None, node_id:int|None=None):
    rows=read_store(); out=[]
    for g in rows:
        if selection_id is not None and g['selection_id']!=selection_id: continue
        if node_id is not None and not any(s['node_id']==node_id for s in g['source_nodes']): continue
        out.append({'generation_id':g['generation_id'],'selection_id':g['selection_id'],'selection_name':g['selection_name'],'created_at':g['created_at'],'case_count':len(g['test_cases']),'staleness':generation_status(g)})
    return {'count':len(out),'generations':out}
@app.get('/generations/{generation_id}')
def get_generation(generation_id:str):
    g=next((x for x in read_store() if x['generation_id']==generation_id),None)
    if not g: raise HTTPException(404,'Generation not found')
    return {**g,'staleness':generation_status(g)}
