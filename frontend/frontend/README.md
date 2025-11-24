# BioNLP Annotation Tool (React + FastAPI)

This project pairs a FastAPI backend with a modern React/Vite frontend to help quickly label biomedical text.  
You can upload documents, highlight spans, assign labels (with ranks), and export your annotations as JSON, TXT, or DOCX.

## Features

- **Flexible document ingestion** – Upload single files, entire folders, ZIP archives, or paste text directly in the browser.
- **Document library** – Search previously uploaded documents, review previews, and reload them for annotation.
- **Inline annotation workflow** – Select text, choose a label, optionally add a rank, and see highlighted spans immediately.
- **Label manager** – Create/update label definitions with custom colors.
- **Exports** – Download annotations as JSON, annotated plain text, or a formatted Word document.

## Tech stack

- Frontend: React 19, Vite, Axios, docx, file-saver
- Backend: FastAPI, Uvicorn, python-docx

## Prerequisites

- Node.js 18+ and npm
- Python 3.10+

## Running the backend

```bash
cd backend
python -m venv .venv
source .venv/bin/activate  # On Windows use: .venv\Scripts\activate
pip install fastapi uvicorn python-multipart python-docx
uvicorn main:app --reload --host 0.0.0.0 --port 8000
```

The API saves data under `backend/data/`:

- `documents.json` – uploaded documents + previews
- `annotations.json` – annotations keyed by `doc_id`
- `labels.json` – label to color map

## Running the frontend

```bash
cd frontend/frontend
npm install
npm run dev
```

The frontend expects the backend at `http://127.0.0.1:8000` (configured in `src/App.jsx`).  
Open the Vite dev URL (usually `http://localhost:5173`) in your browser.

## Usage guide

1. **Upload or paste text** via the Document Library card.
2. **Select a document** from the list on the right to load it into the annotation workspace.
3. **Highlight text** in the document pane: a popup lets you set an optional rank and choose a label.
4. **Manage labels** at the bottom of the page; colors update immediately.
5. **Export** annotations using the buttons below the document view (TXT, JSON, DOCX).

Changes are stored locally in `backend/data/`, so keep that folder if you want to preserve work between sessions.
