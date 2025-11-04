import json
import re
from dataclasses import dataclass, asdict
from typing import List, Dict, Optional

import pandas as pd
import streamlit as st

st.set_page_config(page_title="Medical Notes Annotation", layout="wide")

# ------------------------- Models -------------------------
@dataclass
class Annotation:
    doc_id: str
    start: int
    end: int
    text: str
    label: str

# ------------------------- Helpers -------------------------
DEFAULT_LABELS = ["Diagnosis", "Symptom", "Medication", "Procedure", "Test", "Other"]

def split_docs_from_text(raw: str) -> List[str]:
    """
    Accepts pasted text. If multiple notes are pasted, split by blank line.
    Otherwise treat as single document.
    """
    # Normalize newlines
    raw = raw.replace("\r\n", "\n").strip()
    if "\n\n" in raw:
        docs = [d.strip() for d in raw.split("\n\n") if d.strip()]
    else:
        docs = [raw] if raw else []
    return docs

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

def highlight(text: str, anns: List[Annotation]) -> str:
    """
    Returns HTML with spans highlighted for current annotations.
    """
    if not text:
        return ""
    anns_sorted = sorted(anns, key=lambda a: a.start)
    html = []
    cursor = 0
    for a in anns_sorted:
        # Clamp and sanity check
        s = max(0, min(a.start, len(text)))
        e = max(0, min(a.end, len(text)))
        if s > cursor:
            html.append(st.session_state["escape"](text[cursor:s]))
        bg = color_for(a.label)
        seg = st.session_state["escape"](text[s:e])
        title = st.session_state["escape"](f"{a.label}: {a.text}")
        html.append(
            f'<span title="{title}" style="background:{bg};'
            f'border:1px solid rgba(0,0,0,.12); border-radius:4px; padding:0 2px;">{seg}</span>'
        )
        cursor = e
    if cursor < len(text):
        html.append(st.session_state["escape"](text[cursor:]))
    return "".join(html)

def find_next(haystack: str, needle: str, start_pos: int) -> Optional[re.Match]:
    if not needle.strip():
        return None
    return re.search(re.escape(needle), haystack[start_pos:], flags=re.IGNORECASE)

def to_jsonl(anns_by_doc: Dict[str, List[Annotation]]) -> str:
    lines = []
    for doc_id, items in anns_by_doc.items():
        for a in items:
            lines.append(json.dumps(asdict(a), ensure_ascii=False))
    return "\n".join(lines)

def to_csv(anns_by_doc: Dict[str, List[Annotation]]) -> str:
    rows = []
    for doc_id, items in anns_by_doc.items():
        for a in items:
            rows.append(asdict(a))
    df = pd.DataFrame(rows, columns=["doc_id", "start", "end", "text", "label"])
    return df.to_csv(index=False)

def esc(s: str) -> str:
    return (
        s.replace("&", "&amp;")
         .replace("<", "&lt;")
         .replace(">", "&gt;")
         .replace('"', "&quot;")
    )

# ------------------------- Session State -------------------------
if "docs" not in st.session_state:
    st.session_state.docs: Dict[str, str] = {}         # {doc_id: text}
if "anns" not in st.session_state:
    st.session_state.anns: Dict[str, List[Annotation]] = {}   # {doc_id: [Annotation]}
if "labels" not in st.session_state:
    st.session_state.labels: List[str] = DEFAULT_LABELS.copy()
if "escape" not in st.session_state:
    st.session_state["escape"] = esc

# ------------------------- Sidebar (Data & Labels) -------------------------
with st.sidebar:
    st.header("Data")
    src = st.radio("Load notes from:", ["Paste text", "Upload .txt", "Upload .csv"], index=0)

    if src == "Paste text":
        pasted = st.text_area("Paste medical notes (one note or multiple notes separated by a blank line):", height=180)
        if st.button("Add to workspace", use_container_width=True, type="primary"):
            docs = split_docs_from_text(pasted)
            for i, d in enumerate(docs, start=1):
                doc_id = f"doc_{len(st.session_state.docs)+1:04d}"
                st.session_state.docs[doc_id] = d
                st.session_state.anns.setdefault(doc_id, [])
            st.success(f"Added {len(docs)} note(s).")

    elif src == "Upload .txt":
        up = st.file_uploader("Choose a .txt file", type=["txt"])
        if up and st.button("Add file", use_container_width=True, type="primary"):
            content = up.read().decode("utf-8", errors="ignore")
            docs = split_docs_from_text(content)
            for d in docs:
                doc_id = f"doc_{len(st.session_state.docs)+1:04d}"
                st.session_state.docs[doc_id] = d
                st.session_state.anns.setdefault(doc_id, [])
            st.success(f"Added {len(docs)} note(s).")

    else:  # CSV
        csv = st.file_uploader("Choose a .csv with columns: id,text", type=["csv"])
        if csv and st.button("Add CSV", use_container_width=True, type="primary"):
            df = pd.read_csv(csv)
            if not {"id", "text"}.issubset(df.columns):
                st.error("CSV must have columns: id,text")
            else:
                for _, row in df.iterrows():
                    doc_id = str(row["id"])
                    st.session_state.docs[doc_id] = str(row["text"])
                    st.session_state.anns.setdefault(doc_id, [])
                st.success(f"Added {len(df)} note(s).")

    st.divider()
    st.header("Labels")
    current = st.session_state.labels
    chosen = st.selectbox("Active label", current, index=0)
    new_label = st.text_input("Add new label")
    cols = st.columns(2)
    with cols[0]:
        if st.button("Add label"):
            nl = new_label.strip()
            if nl and nl not in st.session_state.labels:
                st.session_state.labels.append(nl)
                st.success(f"Added label: {nl}")
    with cols[1]:
        if st.button("Reset labels"):
            st.session_state.labels = DEFAULT_LABELS.copy()
            st.success("Labels reset.")

    st.divider()
    st.header("Export")
    jsonl_data = to_jsonl(st.session_state.anns)
    csv_data = to_csv(st.session_state.anns)
    st.download_button("Download JSONL", data=jsonl_data, file_name="annotations.jsonl", mime="application/json")
    st.download_button("Download CSV", data=csv_data, file_name="annotations.csv", mime="text/csv")

# ------------------------- Main UI -------------------------
st.title("Medical Notes Annotation (Streamlit MVP)")

if not st.session_state.docs:
    st.info("Load or paste notes using the sidebar.")
    st.stop()

# ---- Document chooser
doc_ids = list(st.session_state.docs.keys())
left, right = st.columns([2, 1])
with left:
    doc_id = st.selectbox("Select a document", doc_ids, index=0)
with right:
    if st.button("Delete current document", type="secondary"):
        st.session_state.docs.pop(doc_id, None)
        st.session_state.anns.pop(doc_id, None)
        st.rerun()

text = st.session_state.docs[doc_id]
anns = st.session_state.anns.get(doc_id, [])

# ---- Viewer with highlights
st.subheader("Document")
st.markdown(
    f'<div style="padding:12px;border:1px solid #e5e7eb;border-radius:12px;min-height:120px;'
    f'background:#fff;line-height:1.6;">{highlight(text, anns)}</div>',
    unsafe_allow_html=True
)

st.caption(f"Length: {len(text)} characters • {len(anns)} annotation(s)")

st.divider()

# ------------------------- Create annotation -------------------------
st.subheader("Add Annotation")

tab1, tab2 = st.tabs(["By selecting indices (precise)", "By searching text (quick)"])

with tab1:
    c1, c2, c3 = st.columns([1, 1, 2])
    with c1:
        start = st.number_input("Start index", min_value=0, max_value=len(text), value=0, step=1)
    with c2:
        end = st.number_input("End index", min_value=0, max_value=len(text), value=min(len(text), 5), step=1)
    with c3:
        st.text_area("Preview (auto)", value=text[start:end], height=70, key="preview_idx", disabled=True)

    label = st.selectbox("Label", st.session_state.labels, key="label_idx")
    if st.button("Add annotation (indices)", type="primary"):
        if start < end:
            a = Annotation(doc_id=doc_id, start=int(start), end=int(end), text=text[start:end], label=st.session_state["label_idx"])
            st.session_state.anns[doc_id].append(a)
            st.success(f"Added: [{start}, {end}] • {a.label} • “{a.text[:40]}”")
        else:
            st.warning("End index must be greater than start.")

with tab2:
    q = st.text_input("Find text (case-insensitive):", placeholder="e.g., chest pain")
    find_from = st.number_input("Search from index", min_value=0, max_value=len(text), value=0, step=1)
    if st.button("Find next"):
        m = find_next(text, q, int(find_from))
        if m:
            s = int(find_from) + m.start()
            e = int(find_from) + m.end()
            st.session_state["last_search"] = (s, e, text[s:e])
            st.success(f"Found at [{s}, {e}]")
        else:
            st.info("No further matches.")

    found = st.session_state.get("last_search")
    if found:
        s, e, frag = found
        st.write(f"**Match**: [{s}, {e}] → “{frag}”")
        label2 = st.selectbox("Label", st.session_state.labels, key="label_search")
        if st.button("Add annotation (search match)", type="primary"):
            a = Annotation(doc_id=doc_id, start=s, end=e, text=frag, label=label2)
            st.session_state.anns[doc_id].append(a)
            st.success(f"Added: [{s}, {e}] • {label2} • “{frag[:40]}”")

st.divider()

# ------------------------- Existing annotations -------------------------
st.subheader("Annotations for this document")
if not anns:
    st.info("No annotations yet.")
else:
    # Table
    df = pd.DataFrame([asdict(a) for a in anns])
    st.dataframe(df, use_container_width=True, hide_index=True)

    # Delete controls
    idx_to_delete = st.selectbox("Delete by row", options=list(range(len(anns))), format_func=lambda i: f"{i}: {anns[i].label} [{anns[i].start},{anns[i].end}] “{anns[i].text[:30]}”")
    cols = st.columns(2)
    with cols[0]:
        if st.button("Delete selected row", type="secondary"):
            st.session_state.anns[doc_id].pop(idx_to_delete)
            st.rerun()
    with cols[1]:
        if st.button("Clear all for this doc", type="secondary"):
            st.session_state.anns[doc_id] = []
            st.rerun()
