"""LLM generation with strict validation, bounded retries, and JSON-backed persistence."""
import json, uuid
from datetime import datetime, timezone
from pathlib import Path
from app.config import GENERATIONS_JSON, LLM_API_KEY, LLM_MODEL, LLM_PROVIDER
from app.db import SessionLocal
from app.schemas import GenerationPayload

def now(): return datetime.now(timezone.utc).isoformat()

def read_store():
    GENERATIONS_JSON.parent.mkdir(parents=True, exist_ok=True)
    if not GENERATIONS_JSON.exists(): return []
    try: return json.loads(GENERATIONS_JSON.read_text(encoding='utf-8'))
    except (json.JSONDecodeError, OSError): return []

def write_store(rows):
    GENERATIONS_JSON.parent.mkdir(parents=True, exist_ok=True)
    tmp=GENERATIONS_JSON.with_suffix('.tmp')
    tmp.write_text(json.dumps(rows,indent=2,ensure_ascii=False),encoding='utf-8'); tmp.replace(GENERATIONS_JSON)

def local_fallback(source_text: str, node_ids: list[int]) -> dict:
    """Transparent offline fallback; clearly tagged so it is not misrepresented as LLM output."""
    snippet=source_text[:500].strip() or 'Selected source section'
    cases=[]
    templates=[
      ('Nominal behavior','Verify the behavior described in the selected requirement.', ['Set up the device in the documented starting state.','Execute the normal workflow described by the requirement.','Record the displayed result and stored data.'], 'Observed behavior matches the selected requirement.', 'medium'),
      ('Boundary condition','Verify behavior at a stated limit or threshold, if one is specified.', ['Identify the numeric limits stated in the source text.','Exercise the boundary and the immediately adjacent value on each side where safe in simulation.','Capture device response and any error indication.'], 'Boundary behavior is consistent with the source requirement; no undocumented outcome is assumed.', 'high'),
      ('Invalid or interrupted flow','Verify the documented failure or interruption behavior.', ['Configure a controlled test setup for a documented failure condition.','Trigger the condition without exposing a person to risk.','Observe recovery, displayed error, and data integrity.'], 'The documented failure behavior occurs and the device does not report a false successful measurement.', 'high'),
      ('Persistence and repeatability','Check that repeated operation does not contradict the selected requirement.', ['Run the workflow repeatedly in a controlled test environment.','Compare each result against the stated behavior.','Inspect any saved state relevant to the requirement.'], 'Repeated runs remain consistent with the requirement and preserve relevant data.', 'medium'),
      ('Recovery','Check recovery after the documented condition clears.', ['Trigger a documented error condition in simulation.','Follow the manual’s recovery instructions.','Repeat the original operation and record the result.'], 'Recovery follows the documented instructions without silently bypassing a safety condition.', 'high')]
    for title,obj,steps,expected,severity in templates[:4]:
        cases.append({'title':title,'objective':obj+' Source excerpt: '+snippet,'preconditions':['Use a controlled bench/simulation setup; do not test unsafe conditions on a person.'],'steps':steps,'expected_result':expected,'severity':severity,'source_node_ids':node_ids})
    return {'test_cases':cases}

def call_llm(source_text: str, node_ids: list[int]) -> dict:
    if not LLM_API_KEY: return local_fallback(source_text,node_ids)
    prompt = '''You are a medical-device QA test-design assistant. Produce 3-5 concrete test-case IDEAS grounded only in the provided manual text. Do not invent requirements or claim regulatory compliance. For missing specifics say they are unspecified. Return JSON only: {"test_cases":[{"title":"...","objective":"...","preconditions":["..."],"steps":["..."],"expected_result":"...","severity":"critical|high|medium|low","source_node_ids":[1]}]}. Every test must be executable, have observable expected results, and cite the supplied node IDs.\nSOURCE:\n'''+source_text+'\nNODE_IDS:'+json.dumps(node_ids)
    last_error=None
    for attempt in range(2):
        try:
            if LLM_PROVIDER == 'groq':
                from groq import Groq
                client=Groq(api_key=LLM_API_KEY)
                response=client.chat.completions.create(model=LLM_MODEL,messages=[{'role':'user','content':prompt}],temperature=0.1,response_format={'type':'json_object'})
                raw=response.choices[0].message.content
            elif LLM_PROVIDER == 'gemini':
                import requests
                url=f'https://generativelanguage.googleapis.com/v1beta/models/{LLM_MODEL}:generateContent?key={LLM_API_KEY}'
                r=requests.post(url,json={'contents':[{'parts':[{'text':prompt}]}],'generationConfig':{'responseMimeType':'application/json'}},timeout=45); r.raise_for_status()
                raw=r.json()['candidates'][0]['content']['parts'][0]['text']
            else: raise ValueError('Unsupported LLM_PROVIDER; use groq or gemini.')
            parsed=json.loads(raw)
            validated=GenerationPayload.model_validate(parsed)
            for case in validated.test_cases:
                if not case.source_node_ids: case.source_node_ids=node_ids
                if not set(case.source_node_ids).issubset(set(node_ids)): raise ValueError('LLM cited node IDs outside the selection')
            return validated.model_dump()
        except Exception as e:
            last_error=str(e)
            prompt += '\nYour previous response failed validation: '+last_error+'. Return corrected JSON only, with 3-5 valid test cases.'
    raise RuntimeError('LLM response failed structured validation after 2 attempts: '+str(last_error))

def save_generation(selection_id, selection_name, source_nodes, payload):
    rows=read_store()
    # Idempotency policy: each request creates a new immutable generation; repeated calls are auditable and may reflect a new model response.
    record={'generation_id':str(uuid.uuid4()),'selection_id':selection_id,'selection_name':selection_name,'created_at':now(),'provider':LLM_PROVIDER if LLM_API_KEY else 'local-fallback','model':LLM_MODEL if LLM_API_KEY else 'deterministic-template','source_nodes':[{'node_id':n['node_id'],'logical_id':n['logical_id'],'version_id':n['version_id'],'version_number':n['version_number'],'heading':n['heading'],'content_hash':n['content_hash'],'text':n['text']} for n in source_nodes],'test_cases':payload['test_cases']}
    rows.append(record); write_store(rows); return record
