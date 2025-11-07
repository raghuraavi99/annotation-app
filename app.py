# Medical Notes Annotation – Streamlit (Python 3.9+)
# Features:
# - Load: paste / .txt / .csv / .pdf / multiple / .zip / open local directory
# - Interactive selection -> popup labels -> add one/many
# - Search with numbered match badges; add current or ALL matches
# - Labels manager
# - Export JSONL / CSV; Save/Load workspace (relations included)
# - Power labeling: relations (link two spans)
# - Assistive features: gazetteer pre-annotation + PHI finder

from dataclasses import dataclass, asdict, field
from typing import List, Dict, Optional, Tuple
import json
import re
import io
import os
import glob
from zipfile import ZipFile

import pandas as pd
import streamlit as st
from pypdf import PdfReader
import streamlit.components.v1 as components

st.set_page_config(page_title="Medical Notes Annotation", layout="wide")

# ------------------------- Data Model -------------------------
@dataclass
class Annotation:
    doc_id: str
    start: int
    end: int
    text: str
    label: str
    attrs: Dict[str, str] = field(default_factory=dict)  # optional attributes

@dataclass
class Relation:
    doc_id: str
    head_idx: int   # index into st.session_state.anns[doc_id]
    tail_idx: int
    label: str

# ------------------------- Helpers -------------------------
DEFAULT_LABELS = ["Diagnosis", "Symptom", "Medication", "Procedure", "Test", "Other"]

def split_docs_from_text(raw: str) -> List[str]:
    raw = (raw or "").replace("\r\n", "\n").strip()
    if not raw:
        return []
    if "\n\n" in raw:
        return [d.strip() for d in raw.split("\n\n") if d.strip()]
    return [raw]

def color_for(label: str) -> str:
    palette = {
        "Diagnosis": "#cfe8ff",
        "Symptom": "#d7f9e9",
        "Medication": "#fde7c8",
        "Procedure": "#ffe0e6",
        "Test": "#eadcff",
        "Other": "#f0f0f0",
    }
    return palette.get(label, "#f0f0f0")

def to_jsonl(anns_by_doc: Dict[str, List[Annotation]]) -> str:
    lines = []
    for _, items in anns_by_doc.items():
        for a in items:
            lines.append(json.dumps(asdict(a), ensure_ascii=False))
    return "\n".join(lines)

def to_csv(anns_by_doc: Dict[str, List[Annotation]]) -> str:
    rows = []
    for _, items in anns_by_doc.items():
        for a in items:
            rows.append(asdict(a))
    if not rows:
        return "doc_id,start,end,text,label,attrs\n"
    df = pd.DataFrame(rows, columns=["doc_id", "start", "end", "text", "label", "attrs"])
    return df.to_csv(index=False)

def extract_text_from_pdf(file_bytes: bytes) -> str:
    reader = PdfReader(io.BytesIO(file_bytes))
    pages = []
    for p in reader.pages:
        t = p.extract_text() or ""
        pages.append(t.strip())
    return "\n\n".join(pages).strip()

def workspace_to_json(docs: Dict[str, str], anns: Dict[str, List[Annotation]], labels: List[str]) -> str:
    payload = {
        "version": 2,  # include relations
        "docs": docs,
        "anns": {k: [asdict(a) for a in v] for k, v in anns.items()},
        "labels": labels,
        "relations": {
            k: [asdict(r) for r in st.session_state.relations.get(k, [])]
            for k in docs.keys()
        },
    }
    return json.dumps(payload, ensure_ascii=False, indent=2)

def workspace_from_json(s: str):
    data = json.loads(s)
    docs = data.get("docs", {})
    raw_anns = data.get("anns", {})
    anns = {k: [Annotation(**a) for a in v] for k, v in raw_anns.items()}
    labels = data.get("labels", DEFAULT_LABELS.copy())
    raw_rels = data.get("relations", {})
    st.session_state.relations = {k: [Relation(**r) for r in v] for k, v in raw_rels.items()}
    return docs, anns, labels

def _add_doc(text: str) -> None:
    doc_id = f"doc_{len(st.session_state.docs)+1:04d}"
    st.session_state.docs[doc_id] = text
    st.session_state.anns.setdefault(doc_id, [])

# -------- Requirement #1: Ingest an entire local directory --------
def ingest_folder(folder: str, recursive: bool = True) -> int:
    if not folder or not os.path.isdir(folder):
        return -1
    patterns = ["**/*.txt", "**/*.pdf", "**/*.csv"] if recursive else ["*.txt", "*.pdf", "*.csv"]
    paths: List[str] = []
    for pat in patterns:
        paths.extend(glob.glob(os.path.join(folder, pat), recursive=recursive))
    added = 0
    for p in paths:
        low = p.lower()
        try:
            if low.endswith(".txt"):
                with open(p, "r", encoding="utf-8", errors="ignore") as f:
                    content = f.read()
                for d in split_docs_from_text(content):
                    _add_doc(d); added += 1
            elif low.endswith(".pdf"):
                with open(p, "rb") as f:
                    text_from_pdf = extract_text_from_pdf(f.read())
                if text_from_pdf:
                    _add_doc(text_from_pdf); added += 1
            elif low.endswith(".csv"):
                df = pd.read_csv(p)
                if {"id", "text"}.issubset(df.columns):
                    for _, row in df.iterrows():
                        st.session_state.docs[str(row["id"])] = str(row["text"])
                        st.session_state.anns.setdefault(str(row["id"]), [])
                        added += 1
                else:
                    st.warning(f"CSV skipped (needs columns: id,text): {os.path.basename(p)}")
        except Exception as e:
            st.warning(f"Skipped {os.path.basename(p)}: {e}")
    return added

# ------------------------- Search helpers -------------------------
def find_all(haystack: str, needle: str) -> List[Tuple[int, int]]:
    if not needle or not needle.strip():
        return []
    return [(m.start(), m.end()) for m in re.finditer(re.escape(needle), haystack, flags=re.IGNORECASE)]

# ------------------------- Assistive features -------------------------
WORD_BOUND = r"(?<![A-Za-z0-9_])(TERM)(?![A-Za-z0-9_])"

def preannotate_doc(doc_id: str, rules: List[Tuple[str, str]], case_insensitive: bool = True) -> int:
    """rules: list of (label, term_or_regex). Whole-word used for plain terms."""
    flags = re.IGNORECASE if case_insensitive else 0
    txt = st.session_state.docs[doc_id]
    added = 0
    for lbl, term in rules:
        pattern = term
        # treat as plain term if it has no regex metachar
        if not any(ch in term for ch in r".*+?[](){}|\\" ):
            pattern = WORD_BOUND.replace("TERM", re.escape(term))
        for m in re.finditer(pattern, txt, flags):
            s, e = m.start(), m.end()
            frag = txt[s:e]
            st.session_state.anns[doc_id].append(
                Annotation(doc_id, s, e, frag, lbl, attrs={"source": "gazetteer"})
            )
            added += 1
    return added

PHI_RULES = [
    ("PHI_DATE",  r"\b(?:\d{1,2}[/-]\d{1,2}[/-]\d{2,4}|\d{4}[/-]\d{1,2}[/-]\d{1,2}|(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Sept|Oct|Nov|Dec)[a-z]*\s+\d{1,2},?\s+\d{2,4})\b"),
    ("PHI_PHONE", r"\b(?:\+?1[-.\s]?)?(?:\(?\d{3}\)?[-.\s]?)\d{3}[-.\s]?\d{4}\b"),
    ("PHI_EMAIL", r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b"),
    ("PHI_MRN",   r"\b(?:MRN[:#]?\s*)?\d{7,}\b"),
]

# ------------------------- Session -------------------------
if "docs" not in st.session_state:
    st.session_state.docs = {}
if "anns" not in st.session_state:
    st.session_state.anns = {}
if "labels" not in st.session_state:
    st.session_state.labels = DEFAULT_LABELS.copy()
if "search" not in st.session_state:
    st.session_state.search = {}
if "relations" not in st.session_state:
    st.session_state.relations = {}  # type: Dict[str, List[Relation]]

# ------------------------- Sidebar -------------------------
with st.sidebar:
    st.header("📄 Load Data")
    src = st.radio(
        "Load notes from:",
        [
            "Paste text",
            "Upload .txt",
            "Upload .csv",
            "Upload .pdf",
            "Upload multiple (.txt/.pdf/.csv)",
            "Upload .zip (folder)",
            "Open local directory",
        ],
        index=0,
    )

    if src == "Paste text":
        pasted = st.text_area("Paste medical notes (separated by a blank line):", height=180)
        if st.button("Add to workspace", type="primary"):
            docs = split_docs_from_text(pasted)
            for d in docs:
                _add_doc(d)
            st.success(f"✅ Added {len(docs)} note(s).")

    elif src == "Upload .txt":
        up = st.file_uploader("Choose a .txt file", type=["txt"])
        if up and st.button("Add file", type="primary"):
            content = up.read().decode("utf-8", errors="ignore")
            for d in split_docs_from_text(content):
                _add_doc(d)
            st.success("✅ Added note(s) from .txt.")

    elif src == "Upload .csv":
        csvf = st.file_uploader("Choose a .csv with columns: id,text", type=["csv"])
        if csvf and st.button("Add CSV", type="primary"):
            df = pd.read_csv(csvf)
            if not {"id", "text"}.issubset(df.columns):
                st.error("CSV must have columns: id,text")
            else:
                for _, row in df.iterrows():
                    st.session_state.docs[str(row["id"])] = str(row["text"])
                    st.session_state.anns.setdefault(str(row["id"]), [])
                st.success(f"✅ Added {len(df)} note(s) from CSV.")

    elif src == "Upload .pdf":
        up_pdf = st.file_uploader("Choose a PDF file", type=["pdf"])
        if up_pdf and st.button("Add PDF", type="primary"):
            try:
                text_from_pdf = extract_text_from_pdf(up_pdf.read())
                if not text_from_pdf:
                    st.warning("⚠️ No extractable text in this PDF.")
                else:
                    _add_doc(text_from_pdf)
                    st.success("✅ Added 1 PDF as a document.")
            except Exception as e:
                st.error(f"❌ PDF read failed: {e}")

    elif src == "Upload multiple (.txt/.pdf/.csv)":
        files = st.file_uploader(
            "Choose one or more files (.txt, .pdf, .csv)",
            type=["txt", "pdf", "csv"],
            accept_multiple_files=True,
        )
        if files and st.button("Add all files", type="primary"):
            added = 0
            for f in files:
                name = f.name.lower()
                try:
                    if name.endswith(".txt"):
                        content = f.read().decode("utf-8", errors="ignore")
                        for d in split_docs_from_text(content):
                            _add_doc(d); added += 1
                    elif name.endswith(".pdf"):
                        text_from_pdf = extract_text_from_pdf(f.read())
                        if text_from_pdf:
                            _add_doc(text_from_pdf); added += 1
                    elif name.endswith(".csv"):
                        df = pd.read_csv(f)
                        if {"id", "text"}.issubset(df.columns):
                            for _, row in df.iterrows():
                                st.session_state.docs[str(row["id"])] = str(row["text"])
                                st.session_state.anns.setdefault(str(row["id"]), [])
                                added += 1
                        else:
                            st.warning(f"CSV {f.name} skipped (needs columns: id,text).")
                except Exception as e:
                    st.error(f"Failed to read {f.name}: {e}")
            st.success(f"✅ Added {added} note(s) from {len(files)} file(s).")

    elif src == "Upload .zip (folder)":
        up_zip = st.file_uploader("Choose a .zip containing .txt/.pdf/.csv", type=["zip"])
        if up_zip and st.button("Add from .zip", type="primary"):
            added = 0
            try:
                zf = ZipFile(io.BytesIO(up_zip.read()))
                for info in zf.infolist():
                    if info.is_dir(): continue
                    name = info.filename.lower()
                    if not (name.endswith(".txt") or name.endswith(".pdf") or name.endswith(".csv")):
                        continue
                    try:
                        data = zf.read(info)
                        if name.endswith(".txt"):
                            content = data.decode("utf-8", errors="ignore")
                            for d in split_docs_from_text(content):
                                _add_doc(d); added += 1
                        elif name.endswith(".pdf"):
                            text_from_pdf = extract_text_from_pdf(data)
                            if text_from_pdf: _add_doc(text_from_pdf); added += 1
                        elif name.endswith(".csv"):
                            df = pd.read_csv(io.BytesIO(data))
                            if {"id", "text"}.issubset(df.columns):
                                for _, row in df.iterrows():
                                    st.session_state.docs[str(row["id"])] = str(row["text"])
                                    st.session_state.anns.setdefault(str(row["id"]), [])
                                    added += 1
                            else:
                                st.warning(f"CSV {info.filename} skipped (needs columns: id,text).")
                    except Exception as e:
                        st.warning(f"Skipping {info.filename}: {e}")
                st.success(f"✅ Added {added} note(s) from ZIP.")
            except Exception as e:
                st.error(f"Could not read ZIP: {e}")

    elif src == "Open local directory":
        st.caption("Reads files directly from your computer (works when running locally).")
        folder = st.text_input("Folder path", placeholder="/Users/yourname/path/to/folder")
        recursive = st.checkbox("Search subfolders (recursive)", value=True)
        if st.button("Ingest folder", type="primary"):
            count = ingest_folder(folder.strip(), recursive=recursive)
            if count == -1:
                st.error("Folder not found or not accessible. Double-check the path.")
            else:
                st.success(f"✅ Added {count} note(s) from the folder.")
                if count > 0:
                    st.rerun()

    st.divider()
    st.header("📤 Export")
    st.download_button("⬇️ Download JSONL", data=to_jsonl(st.session_state.anns),
                       file_name="annotations.jsonl", mime="application/json")
    st.download_button("⬇️ Download CSV", data=to_csv(st.session_state.anns),
                       file_name="annotations.csv", mime="text/csv")

    st.divider()
    st.header("💾 Workspace")
    ws_json = workspace_to_json(st.session_state.docs, st.session_state.anns, st.session_state.labels)
    st.download_button("Save Workspace (.json)", data=ws_json,
                       file_name="workspace.json", mime="application/json")
    ws_file = st.file_uploader("Load Workspace (.json)", type=["json"], key="ws_upload")
    if ws_file and st.button("Load Workspace", type="secondary"):
        try:
            content = ws_file.read().decode("utf-8", errors="ignore")
            docs2, anns2, labels2 = workspace_from_json(content)
            st.session_state.docs = docs2
            st.session_state.anns = anns2
            st.session_state.labels = labels2
            st.success("✅ Workspace loaded.")
            st.rerun()
        except Exception as e:
            st.error(f"Failed to load workspace: {e}")

    st.divider()
    st.header("🏷️ Labels")
    _ = st.selectbox("Active label (for manual tabs below)", st.session_state.labels, index=0, key="active_label")
    new_label = st.text_input("Add new label")
    c1, c2 = st.columns(2)
    if c1.button("Add label"):
        nl = new_label.strip()
        if nl and nl not in st.session_state.labels:
            st.session_state.labels.append(nl)
            st.success(f"✅ Added label: {nl}")
    if c2.button("Reset labels"):
        st.session_state.labels = DEFAULT_LABELS.copy()
        st.success("Labels reset.")

    st.divider()
    st.header("🧠 Assistive labeling")
    st.caption("Gazetteer (CSV with columns **label,term**) – auto-tag terms.")
    gaz_up = st.file_uploader("Upload gazetteer CSV", type=["csv"], key="gaz")
    scoped = st.radio("Scope", ["Current doc", "All docs"], horizontal=True)
    casei = st.checkbox("Case-insensitive", value=True)
    if st.button("Run gazetteer pre-annotation", type="primary", disabled=(gaz_up is None)):
        try:
            df_g = pd.read_csv(gaz_up)
            if not {"label", "term"}.issubset(df_g.columns):
                st.error("CSV must have columns: label,term")
            else:
                rules = [(str(r["label"]), str(r["term"])) for _, r in df_g.iterrows()]
                total = 0
                targets = [st.session_state.get("last_doc_id")] if scoped == "Current doc" else list(st.session_state.docs.keys())
                # fallback if first time
                if not targets or targets == [None]:
                    targets = list(st.session_state.docs.keys())
                for did in targets:
                    total += preannotate_doc(did, rules, case_insensitive=casei)
                st.success(f"✅ Added {total} suggestions from gazetteer.")
                st.rerun()
        except Exception as e:
            st.error(f"Failed to read gazetteer: {e}")

    st.caption("Quick PHI finder (creates PHI_* annotations for common patterns).")
    phi_scope = st.radio("PHI scope", ["Current doc", "All docs"], horizontal=True, key="phi_scope")
    if st.button("Run PHI finder", type="secondary"):
        rules = PHI_RULES
        total = 0
        targets = [st.session_state.get("last_doc_id")] if st.session_state.get("phi_scope") == "Current doc" else list(st.session_state.docs.keys())
        if not targets or targets == [None]:
            targets = list(st.session_state.docs.keys())
        for did in targets:
            total += preannotate_doc(did, rules, case_insensitive=True)
        st.success(f"✅ Added {total} PHI annotations.")
        st.rerun()

# ------------------------- Main -------------------------
st.title("💻 BioNLP Annotation Tool")

if not st.session_state.docs:
    st.info("👉 Load or paste notes using the sidebar.")
    st.stop()

doc_ids = list(st.session_state.docs.keys())
left, right = st.columns([2, 1])
with left:
    doc_id = st.selectbox("Select a document", doc_ids, index=0, key="doc_select")
st.session_state.last_doc_id = doc_id
with right:
    if st.button("🗑️ Delete current document"):
        st.session_state.docs.pop(doc_id, None)
        st.session_state.anns.pop(doc_id, None)
        st.session_state.relations.pop(doc_id, None)
        st.rerun()

text = st.session_state.docs[doc_id]
anns = st.session_state.anns.get(doc_id, [])

# Search state
if doc_id not in st.session_state.search:
    st.session_state.search[doc_id] = {"term": "", "positions": [], "i": 0}
sstate = st.session_state.search[doc_id]
positions: List[Tuple[int, int]] = sstate.get("positions", []) or []
match_map: Dict[str, int] = {f"{s}-{e}": idx + 1 for idx, (s, e) in enumerate(positions)}
match_total = len(positions)

# ------------------------- Interactive Viewer -------------------------
st.subheader("📝 Document (select text to label)")

viewer_payload = {
    "text": text,
    "labels": st.session_state.labels,
    "annotations": [asdict(a) for a in anns],
    "match_index_map": match_map,
    "match_total": match_total
}
# Important: compute JSON outside the f-string (avoid backslash in f-string expr)
payload_json = json.dumps(viewer_payload).replace("</", "<\\/")

component_html = f"""
<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8" />
<style>
  body {{ margin:0; font-family: -apple-system, Segoe UI, Roboto, sans-serif; }}
  .wrap {{
    border:1px solid #e5e7eb; border-radius:12px; background:#fff;
    padding:12px; white-space:pre-wrap; line-height:1.6; position:relative;
  }}
  .ann {{ border:1px solid rgba(0,0,0,.12); border-radius:4px; padding:0 2px; }}
  .badge {{
    display:inline-block;margin-left:4px;font-size:10px;line-height:1;
    color:#444;background:#f3f4f6;border:1px solid #e5e7eb;border-radius:6px;
    padding:2px 4px;vertical-align:baseline;
  }}
  #popup {{
    position:absolute; z-index:9999; background:#111827; color:white;
    padding:6px 8px; border-radius:8px; display:none; gap:6px; flex-wrap:wrap;
    box-shadow:0 8px 24px rgba(0,0,0,.18);
  }}
  #popup button {{
    background:#f9fafb; color:#111827; border:1px solid #e5e7eb; border-radius:6px;
    padding:3px 6px; cursor:pointer;
  }}
  #popup .apply {{ background:#2563eb; color:#fff; border:none; }}
</style>
</head>
<body>
<div id="root" class="wrap"></div>
<div id="popup"></div>

<script>
const payload = {payload_json};

const root = document.getElementById('root');
const popup = document.getElementById('popup');
const text = payload.text || "";

// Render annotations and badges
function renderAnnotated() {{
  const anns = (payload.annotations || []).slice().sort((a,b)=>a.start-b.start);
  let cursor = 0;
  root.innerHTML = "";
  function appendText(t) {{
    if (!t) return;
    root.appendChild(document.createTextNode(t));
  }}
  function labelColor(lbl) {{
    const colors = {{
      "Diagnosis":"#cfe8ff", "Symptom":"#d7f9e9", "Medication":"#fde7c8",
      "Procedure":"#ffe0e6", "Test":"#eadcff", "Other":"#f0f0f0"
    }};
    return colors[lbl] || "#f0f0f0";
  }}
  for (const a of anns) {{
    const s = Math.max(0, Math.min(a.start, text.length));
    const e = Math.max(0, Math.min(a.end, text.length));
    if (s > cursor) appendText(text.slice(cursor, s));
    const span = document.createElement('span');
    span.className = 'ann';
    span.style.background = labelColor(a.label);
    span.title = a.label + ": " + text.slice(s, e);
    const key = s + "-" + e;
    span.appendChild(document.createTextNode(text.slice(s, e)));
    if (payload.match_index_map && payload.match_index_map[key] && payload.match_total) {{
      const sup = document.createElement('sup');
      sup.className = 'badge';
      sup.textContent = payload.match_index_map[key] + "/" + payload.match_total;
      span.appendChild(sup);
    }}
    root.appendChild(span);
    cursor = e;
  }}
  if (cursor < text.length) appendText(text.slice(cursor));
}}

function indexInRoot(node, offset) {{
  const walker = document.createTreeWalker(root, NodeFilter.SHOW_TEXT, null);
  let idx = 0;
  while (true) {{
    const n = walker.nextNode();
    if (!n) break;
    if (n === node) {{
      return idx + offset;
    }}
    idx += n.textContent.length;
  }}
  return null;
}}

function clearPopup() {{
  popup.style.display = 'none';
  popup.innerHTML = '';
}}

function showPopupAt(range) {{
  const rect = range.getBoundingClientRect();
  const rootRect = root.getBoundingClientRect();
  popup.style.left = (rect.left - rootRect.left) + 'px';
  popup.style.top = (rect.bottom - rootRect.top + 6) + 'px';
  popup.style.display = 'flex';
  popup.innerHTML = '';
  const selectedLabels = new Set();
  (payload.labels || []).forEach(lbl => {{
    const btn = document.createElement('button');
    btn.textContent = lbl;
    btn.onclick = () => {{
      if (selectedLabels.has(lbl)) {{
        selectedLabels.delete(lbl);
        btn.style.outline = '';
      }} else {{
        selectedLabels.add(lbl);
        btn.style.outline = '2px solid #2563eb';
      }}
    }};
    popup.appendChild(btn);
  }});
  const apply = document.createElement('button');
  apply.className = 'apply';
  apply.textContent = 'Add';
  apply.onclick = () => {{
    if (!selectedLabels.size) return;
    const sel = window.getSelection();
    if (!sel || sel.rangeCount === 0) return;
    const r = sel.getRangeAt(0);
    const start = indexInRoot(r.startContainer, r.startOffset);
    const end = indexInRoot(r.endContainer, r.endOffset);
    if (start == null || end == null) return;
    const s = Math.min(start, end);
    const e = Math.max(start, end);
    const txt = text.slice(s, e);
    const labels = Array.from(selectedLabels);
    const msg = {{ start:s, end:e, text:txt, labels:labels }};
    window.parent.postMessage({{ isStreamlitMessage:true, type:'streamlit:setComponentValue', value: msg }}, '*');
    clearPopup();
    window.getSelection().removeAllRanges();
  }};
  popup.appendChild(apply);
}}

root.addEventListener('mouseup', () => {{
  const sel = window.getSelection();
  if (!sel || sel.rangeCount === 0) {{ clearPopup(); return; }}
  const r = sel.getRangeAt(0);
  if (r.collapsed) {{ clearPopup(); return; }}
  if (!root.contains(r.startContainer) || !root.contains(r.endContainer)) {{
    clearPopup(); return;
  }}
  showPopupAt(r);
}});

renderAnnotated();
</script>
</body>
</html>
"""

event = components.html(component_html, height=400, scrolling=True)

if isinstance(event, dict) and "start" in event and "end" in event and "labels" in event:
    s, e, frag = int(event["start"]), int(event["end"]), str(event.get("text", ""))
    for lbl in list(event["labels"]):
        ann = Annotation(doc_id, s, e, frag, lbl)
        st.session_state.anns.setdefault(doc_id, []).append(ann)
    st.success(f"✅ Added {len(event['labels'])} annotation(s) for “{frag[:40]}”.")
    st.rerun()

st.caption(f"Length: {len(text)} characters • {len(anns)} annotation(s)")

st.divider()
st.subheader("🔎 Search & Quick Add")

tab1, tab2 = st.tabs(["Search in document", "Add by indices"])

with tab1:
    q2 = st.text_input("Find text", placeholder="e.g., chest pain")
    col_a, col_b, col_c = st.columns([1,1,1])
    if col_a.button("Find all"):
        sstate["term"] = q2
        sstate["positions"] = find_all(text, q2) if q2.strip() else []
        sstate["i"] = 0
    if col_b.button("Prev"):
        if sstate["positions"]:
            sstate["i"] = (sstate["i"] - 1) % len(sstate["positions"])
    if col_c.button("Next"):
        if sstate["positions"]:
            sstate["i"] = (sstate["i"] + 1) % len(sstate["positions"])
    if sstate["positions"]:
        cur = sstate["i"] + 1
        total = len(sstate["positions"])
        s, e = sstate["positions"][sstate["i"]]
        frag = text[s:e]
        st.success(f"Match {cur} of {total}: “{frag}” [{s},{e}]")
        label_s = st.selectbox("Label", st.session_state.labels, key="label_search")
        c1, c2 = st.columns([1,1])
        if c1.button("Add annotation (current match)", type="primary"):
            st.session_state.anns[doc_id].append(Annotation(doc_id, s, e, frag, label_s))
            st.success(f"✅ Added: {label_s} – “{frag[:30]}”")
            st.rerun()
        if c2.button("Annotate **ALL** matches in this document", type="secondary"):
            for (ss, ee) in sstate["positions"]:
                frag2 = text[ss:ee]
                st.session_state.anns[doc_id].append(
                    Annotation(doc_id, ss, ee, frag2, label_s, attrs={"source": "batch-search"})
                )
            st.success(f"✅ Added {len(sstate['positions'])} {label_s} annotations (all matches).")
            st.rerun()
    else:
        st.info("Click **Find all** to collect matches for the current query.")

with tab2:
    c1, c2, c3 = st.columns([1,1,2])
    with c1:
        start = st.number_input("Start index", min_value=0, max_value=len(text), value=0)
    with c2:
        end = st.number_input("End index", min_value=0, max_value=len(text), value=min(5,len(text)))
    with c3:
        st.text_area("Preview", value=text[start:end], height=70, disabled=True)
    label_idx = st.selectbox("Label", st.session_state.labels, key="label_idx")
    if st.button("Add annotation (indices)", type="primary"):
        if start < end:
            a = Annotation(doc_id, int(start), int(end), text[start:end], label_idx)
            st.session_state.anns[doc_id].append(a)
            st.success(f"✅ Added: {label_idx} – “{a.text[:30]}”")
            st.rerun()
        else:
            st.warning("⚠️ End index must be greater than start index.")

st.divider()
st.subheader("📋 Annotations for this document")
anns = st.session_state.anns.get(doc_id, [])
if not anns:
    st.info("No annotations yet.")
else:
    df = pd.DataFrame([asdict(a) for a in anns])
    st.dataframe(df, use_container_width=True, hide_index=True)

# ------------------------- Relations UI -------------------------
st.divider()
st.subheader("🔗 Relations")
rels = st.session_state.relations.setdefault(doc_id, [])
ann_list = [
    f"{i}: [{a.start},{a.end}] {a.label} – {a.text[:40].replace(chr(10),' ')}"
    for i, a in enumerate(st.session_state.anns.get(doc_id, []))
]
if len(ann_list) < 2:
    st.info("Create at least two annotations to link a relation.")
else:
    r1, r2 = st.columns(2)
    with r1:
        head_pick = st.selectbox("Head span", ann_list, key="rel_head")
    with r2:
        tail_pick = st.selectbox("Tail span", ann_list, key="rel_tail")
    rel_label = st.text_input("Relation label", value="relates_to")
    if st.button("Add relation", type="primary"):
        hi = int(head_pick.split(":")[0]); ti = int(tail_pick.split(":")[0])
        if hi == ti:
            st.warning("Pick two different annotations.")
        else:
            rels.append(Relation(doc_id, hi, ti, rel_label))
            st.success("✅ Relation added.")
            st.rerun()

if rels:
    rel_df = pd.DataFrame([asdict(r) for r in rels])
    st.dataframe(rel_df, use_container_width=True, hide_index=True)
