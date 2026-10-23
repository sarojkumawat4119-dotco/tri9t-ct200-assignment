"""CT-200-specific PDF parser. Uses the PDF text layer first, OCR only for image-only pages."""
import hashlib, re
from pathlib import Path
import fitz
try:
    import pytesseract
    from PIL import Image
    import io
except Exception:
    pytesseract = None

# Numbered headings are the primary structural signal. Titles without a number are handled separately.
HEADING_RE = re.compile(r'^\s*(\d+(?:\.\d+)*\.?)\s+(.+?)\s*$')
TABLE_HINTS = {'Parameter', 'Code'}

def sha256(text: str) -> str:
    canonical = re.sub(r'\s+', ' ', normalize(text)).strip()
    return hashlib.sha256(canonical.encode('utf-8')).hexdigest()

def normalize(text: str) -> str:
    text = text.replace('\uFB01','fi').replace('\uFB02','fl').replace('\uFB00','ff')
    text = text.replace('\u00ad','').replace('\ufeff','')
    text = re.sub(r'[\t ]+', ' ', text)
    text = re.sub(r' *\n *', '\n', text)
    return text.strip()

def extract_pages(pdf_path: str | Path):
    doc = fitz.open(pdf_path)
    pages=[]
    for i, page in enumerate(doc, 1):
        text = page.get_text('text', sort=True).strip()
        # OCR fallback for pages without a usable text layer; do not silently treat blank OCR as success.
        if len(text) < 20 and pytesseract is not None:
            pix = page.get_pixmap(matrix=fitz.Matrix(2,2), alpha=False)
            image = Image.open(io.BytesIO(pix.tobytes('png')))
            text = pytesseract.image_to_string(image)
        pages.append((i, normalize(text)))
    return pages

def parse_pdf(pdf_path: str | Path):
    pages = extract_pages(pdf_path)
    # Flatten lines while retaining page markers; join broken lines within paragraphs later.
    lines=[]
    for page_num, text in pages:
        for line in text.splitlines():
            line=line.strip()
            if line: lines.append((page_num,line))
    if not lines: raise ValueError('No extractable text found; OCR fallback returned an empty document.')
    title_parts=[]
    idx=0
    while idx < len(lines) and not HEADING_RE.match(lines[idx][1]):
        title_parts.append(lines[idx][1]); idx+=1
    title=' '.join(title_parts).strip() or 'CT-200 Manual'
    nodes=[{'number':'', 'heading':title, 'level':0, 'body_text':'', 'parent_index':None, 'page_start':lines[0][0], 'page_end':lines[0][0], 'node_type':'document'}]
    stack={0:0}; current=0; pending=[]; pending_start=None; last_top_num=0
    def flush():
        nonlocal pending,pending_start
        if pending:
            chunk='\n'.join(x for _,x in pending)
            if chunk:
                old=nodes[current]['body_text']
                nodes[current]['body_text']=(old+'\n\n'+chunk).strip() if old else chunk
                nodes[current]['page_end']=pending[-1][0]
            pending=[]; pending_start=None
    for page_num,line in lines[idx:]:
        match=HEADING_RE.match(line)
        # Detect a numbered heading only when it is a short standalone line; this avoids treating list items as sections.
        is_heading = bool(match and len(line) < 100 and not line.endswith(('.', ':', ';')))
        if is_heading:
            number, heading=match.group(1).rstrip('.'), match.group(2).strip()
            if ':' in heading: is_heading = False
            # Bare integers inside a section are usually numbered list items (e.g. BP classifications).
            # Accept a bare integer only when it advances the document's top-level section sequence.
            if '.' not in number and int(number) <= last_top_num:
                is_heading = False
        if is_heading:
            flush()
            number, heading=match.group(1).rstrip('.'), match.group(2).strip()
            level=number.count('.')+1
            if level == 1: last_top_num = int(number)
            # Parent is nearest existing numeric prefix. Numbering gaps are retained and explicitly not fabricated.
            parent_index=0
            parts=number.split('.')
            for depth in range(len(parts)-1,0,-1):
                prefix='.'.join(parts[:depth])
                if prefix in stack:
                    parent_index=stack[prefix]; break
            node={'number':number,'heading':heading,'level':level,'body_text':'','parent_index':parent_index,'page_start':page_num,'page_end':page_num,'node_type':'section'}
            node_index=len(nodes); nodes.append(node); stack[number]=node_index; current=node_index
            # Remove stale descendants from stack so a repeated number does not attach to an old subtree.
            for key in list(stack):
                if isinstance(key, str) and key != number and key.startswith(number+'.'): del stack[key]
        else:
            # Keep lists/table rows as literal body text. Form-feed/page boundaries are already removed by PyMuPDF.
            if pending_start is None: pending_start=page_num
            # Join a line-ending hyphen only where it is a PDF line-wrap artifact; retain semantic hyphens elsewhere.
            if pending and pending[-1][1].endswith('-') and line[:1].islower():
                prev_page, prev_line=pending[-1]
                pending[-1]=(prev_page,prev_line[:-1]+line)
            else: pending.append((page_num,line))
    flush()
    # A numbered title can recur in a different parent; each physical occurrence remains a distinct node.
    for n in nodes: n['content_hash']=sha256(n['heading']+'\n'+n['body_text'])
    return nodes
