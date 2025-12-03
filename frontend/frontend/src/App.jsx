import { useState, useEffect, useRef } from "react";
import axios from "axios";
import { Document, Packer, Paragraph, TextRun } from "docx";
import { saveAs } from "file-saver";

const API_BASE = "http://127.0.0.1:8000";

function App() {
  const [message, setMessage] = useState("");
  const [uploadedText, setUploadedText] = useState("");
  const [docId, setDocId] = useState(null);

  const [annotations, setAnnotations] = useState([]);
  const [labels, setLabels] = useState({}); // { name: color }

  const [documents, setDocuments] = useState([]);
  const [searchQuery, setSearchQuery] = useState("");
  const [selectedDocs, setSelectedDocs] = useState([]);

  // Label manager inputs
  const [newLabelName, setNewLabelName] = useState("");
  const [newLabelColor, setNewLabelColor] = useState("#ffff99");

  // Manual paste
  const [manualText, setManualText] = useState("");
  const [manualFilename, setManualFilename] = useState("manual_text.txt");

  // Popup for label selection
  const [popup, setPopup] = useState({
    visible: false,
    top: 0,
    left: 0,
    selection: null, // { text, start, end }
    rank: "",
  });

  
const popupRef = useRef(null);


  // Sidebar state (collapsible)
  const [sidebarOpen, setSidebarOpen] = useState(true);

  // ----------------- Backend check (simple) -----------------

  const testAPI = async () => {
    try {
      const res = await axios.get(`${API_BASE}/documents`);
      setMessage(
        `Backend OK – ${Array.isArray(res.data) ? res.data.length : 0} document(s)`
      );
    } catch (error) {
      console.error(error);
      setMessage("Error: cannot connect to backend");
    }
  };

  // ----------------- Helpers: load docs / labels / annotations -----------------

  const loadDocuments = async () => {
  try {
    const res = await axios.get(`${API_BASE}/documents`);

    const docs = Array.isArray(res.data) ? res.data : [];
    setDocuments(docs);
    setSelectedDocs((prev) =>
      prev.filter((id) => docs.some((doc) => doc.doc_id === id))
    );

  } catch (e) {
    console.error("Failed to load documents:", e);
    setDocuments([]);
  }
};

  const fetchLabels = async () => {
    try {
      const res = await axios.get(`${API_BASE}/labels`);
      setLabels(res.data || {});
    } catch (e) {
      console.error("Failed to load labels", e);
    }
  };

  const fetchAnnotations = async (docIdValue) => {
    if (!docIdValue) return;
    try {
      const encodedId = encodeURIComponent(docIdValue);
      const res = await axios.get(`${API_BASE}/annotations/${encodedId}`);
      setAnnotations(res.data || []);
    } catch (e) {
      console.error("Failed to load annotations", e);
    }
  };

  useEffect(() => {
    loadDocuments();
    fetchLabels();
  }, []);

  // ----------------- Uploads -----------------

  const handleFileUpload = async (event) => {
    const file = event.target.files[0];
    if (!file) return;

    const formData = new FormData();
    formData.append("file", file);

    try {
      const res = await axios.post(`${API_BASE}/upload`, formData, {
        headers: { "Content-Type": "multipart/form-data" },
      });

      const text = (res.data.text || "").replace(/\r\n/g, "\n");
      const docIdValue = res.data.doc_id;

      setUploadedText(text);
      setDocId(docIdValue);
      await fetchAnnotations(docIdValue);
      await loadDocuments();
    } catch (error) {
      console.error(error);
      alert("Upload failed – check backend logs.");
    } finally {
      event.target.value = "";
    }
  };

  const handleZipUpload = async (event) => {
    const file = event.target.files[0];
    if (!file) return;

    const formData = new FormData();
    formData.append("file", file);

    try {
      const res = await axios.post(`${API_BASE}/upload-zip`, formData, {
        headers: { "Content-Type": "multipart/form-data" },
      });
      await loadDocuments();
      alert(`Uploaded ${res.data.saved?.length || 0} documents from zip.`);
    } catch (e) {
      console.error("ZIP upload failed", e);
      alert("ZIP upload failed.");
    } finally {
      event.target.value = "";
    }
  };

  const handleFolderUpload = async (event) => {
    const files = event.target.files;
    if (!files || files.length === 0) return;

    const formData = new FormData();
    for (const file of files) {
      formData.append("files", file);
    }

    try {
      const res = await axios.post(`${API_BASE}/upload-multi`, formData, {
        headers: { "Content-Type": "multipart/form-data" },
      });
      await loadDocuments();
      alert(`Uploaded ${res.data.saved?.length || files.length} files.`);
    } catch (e) {
      console.error("Folder upload failed", e);
      alert("Folder upload failed.");
    } finally {
      event.target.value = "";
    }
  };

  // ----------------- Manual paste -----------------

  const handleManualSubmit = async () => {
    if (!manualText.trim()) {
      alert("Please paste some text first.");
      return;
    }

    try {
      const blob = new Blob([manualText], { type: "text/plain" });
      const file = new File([blob], manualFilename || "manual_text.txt", {
        type: "text/plain",
      });
      const formData = new FormData();
      formData.append("file", file);

      const res = await axios.post(`${API_BASE}/upload`, formData, {
        headers: { "Content-Type": "multipart/form-data" },
      });

      const text = (res.data.text || "").replace(/\r\n/g, "\n");
      const docIdValue = res.data.doc_id;

      setUploadedText(text);
      setDocId(docIdValue);
      setManualText("");
      await fetchAnnotations(docIdValue);
      await loadDocuments();

      alert("Text saved as a new document!");
    } catch (e) {
      console.error("Manual text submit failed", e);
      alert("Failed to save text.");
    }
  };

  // ----------------- Select document -----------------

  const handleSelectDocument = async (docIdValue) => {
    try {
      const encodedId = encodeURIComponent(docIdValue);
      const res = await axios.get(`${API_BASE}/document/${encodedId}`);
      const text = (res.data.text || "").replace(/\r\n/g, "\n");
      setUploadedText(text);
      setDocId(docIdValue);
      await fetchAnnotations(docIdValue);
    } catch (e) {
      console.error("Failed to load document", e);
      alert("Could not load document.");
    }
  };

  // ----------------- Selection & popup -----------------

  // ---------------- Selection & popup ----------------
useEffect(() => {
    if (!uploadedText) return;

    const handleMouseUp = (event) => {
        if (popupRef.current && popupRef.current.contains(event.target)) {
            return;
        }

        const sel = window.getSelection();
        if (!sel || sel.isCollapsed) {
            setPopup(p => ({ ...p, visible: false }));
            return;
        }

        const selectedText = sel.toString();
        if (!selectedText.trim()) {
            setPopup(p => ({ ...p, visible: false }));
            return;
        }

        const startIndex = uploadedText.indexOf(selectedText);
        if (startIndex === -1) {
            setPopup(p => ({ ...p, visible: false }));
            return;
        }

        const endIndex = startIndex + selectedText.length;

        try {
            const range = sel.getRangeAt(0);
            const rect = range.getBoundingClientRect();

            setPopup({
                visible: true,
                top: rect.top - 50,
                left: rect.left,
                selection: { text: selectedText, start: startIndex, end: endIndex },
                rank: ""   // keep rank field
            });
        } catch (e) {
            console.error(e);
        }
    };

    document.addEventListener("mouseup", handleMouseUp);
    return () => document.removeEventListener("mouseup", handleMouseUp);
}, [uploadedText]);


  // ----------------- Save annotation -----------------

  const handleLabelClick = async (labelName) => {
    if (!popup.selection || !docId) return;

    const { start, end, text } = popup.selection;

    const formData = new FormData();
    formData.append("doc_id", docId);
    formData.append("start", String(start));
    formData.append("end", String(end));
    formData.append("text", text);
    formData.append("label", labelName);
    formData.append("rank", popup.rank || "");

    try {
      await axios.post(`${API_BASE}/save-annotation`, formData);
      await fetchAnnotations(docId);
    } catch (e) {
      console.error("Failed to save annotation", e);
      alert("Could not save annotation.");
    }

    setPopup({ visible: false, selection: null });
  };

  // ----------------- Label manager -----------------

  const handleAddLabel = async () => {
    if (!newLabelName.trim()) return;

    const formData = new FormData();
    formData.append("name", newLabelName.trim());
    formData.append("color", newLabelColor || "#ffff99");

    try {
      await axios.post(`${API_BASE}/labels`, formData);
      await fetchLabels();
      setNewLabelName("");
      setNewLabelColor("#ffff99");
    } catch (e) {
      console.error("Failed to add label", e);
      alert("Could not add label.");
    }
  };

  const handleDeleteLabel = async (labelName) => {
    if (!labelName) return;
    const confirmed = window.confirm(
      `Delete label "${labelName}"? This does not modify already-saved annotations.`
    );
    if (!confirmed) return;

    try {
      await axios.delete(`${API_BASE}/labels/${encodeURIComponent(labelName)}`);
      await fetchLabels();
    } catch (e) {
      console.error("Failed to delete label", e);
      alert("Could not delete label.");
    }
  };

  // ----------------- Downloads -----------------

  const downloadAnnotations = () => {
    if (!annotations.length) {
      alert("No annotations to download.");
      return;
    }
    const blob = new Blob([JSON.stringify(annotations, null, 2)], {
      type: "application/json",
    });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = `${docId || "document"}_annotations.json`;
    a.click();
    URL.revokeObjectURL(url);
  };

  const buildAnnotatedString = () => {
    if (!uploadedText) return "";
    if (!annotations.length) return uploadedText;

    let finalText = "";
    let index = 0;
    const sorted = [...annotations].sort((a, b) => a.start - b.start);

    for (const ann of sorted) {
      finalText += uploadedText.slice(index, ann.start);
      finalText += `${ann.text} [${ann.label}]`;
      index = ann.end;
    }
    finalText += uploadedText.slice(index);
    return finalText;
  };

  const downloadAnnotatedText = () => {
    if (!uploadedText) {
      alert("No document loaded.");
      return;
    }

    const finalText = buildAnnotatedString();
    const blob = new Blob([finalText], { type: "text/plain" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = `${docId || "document"}_annotated.txt`;
    a.click();
    URL.revokeObjectURL(url);
  };

  const downloadWordDocument = () => {
    if (!uploadedText) {
      alert("No document loaded.");
      return;
    }

    const finalText = buildAnnotatedString();
    const paragraphs = [];

    // Title
    paragraphs.push(
      new Paragraph({
        children: [
          new TextRun({
            text: "Annotated Document",
            bold: true,
            size: 28,
          }),
        ],
      })
    );

    paragraphs.push(new Paragraph("")); // blank line

    // Main annotated text
    paragraphs.push(
      new Paragraph({
        children: [new TextRun({ text: finalText })],
      })
    );

    paragraphs.push(new Paragraph("")); // blank line

    // Annotation summary
    paragraphs.push(
      new Paragraph({
        children: [
          new TextRun({
            text: "Annotations:",
            bold: true,
            size: 24,
          }),
        ],
      })
    );

    if (!annotations.length) {
      paragraphs.push(
        new Paragraph({
          children: [new TextRun("No annotations.")],
        })
      );
    } else {
      annotations.forEach((ann, idx) => {
        const line = `${idx + 1}. "${ann.text}"  [${ann.label}]  (start: ${
          ann.start
        }, end: ${ann.end})`;
        paragraphs.push(
          new Paragraph({
            children: [new TextRun(line)],
          })
        );
      });
    }

    const doc = new Document({
      sections: [
        {
          properties: {},
          children: paragraphs,
        },
      ],
    });

    Packer.toBlob(doc).then((blob) => {
      saveAs(blob, `${docId || "document"}_annotated.docx`);
    });
  };

  const toggleDocSelection = (docId) => {
    setSelectedDocs((prev) =>
      prev.includes(docId)
        ? prev.filter((id) => id !== docId)
        : [...prev, docId]
    );
  };

  const downloadSelectedDocuments = () => {
    if (!selectedDocs.length) {
      alert("Select at least one document first.");
      return;
    }
    const payload = selectedDocs
      .map((id) => documents.find((doc) => doc.doc_id === id))
      .filter(Boolean)
      .map(({ doc_id, filename, text }) => ({ doc_id, filename, text }));
    if (!payload.length) {
      alert("Selected documents are unavailable.");
      return;
    }
    const blob = new Blob([JSON.stringify(payload, null, 2)], {
      type: "application/json",
    });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = "selected_documents.json";
    a.click();
    URL.revokeObjectURL(url);
  };

  const downloadSelectedAnnotations = async () => {
    if (!selectedDocs.length) {
      alert("Select at least one document to download annotations.");
      return;
    }
    try {
      const entries = await Promise.all(
        selectedDocs.map(async (docId) => {
          const encodedId = encodeURIComponent(docId);
          const res = await axios.get(`${API_BASE}/annotations/${encodedId}`);
          return { doc_id: docId, annotations: res.data || [] };
        })
      );
      const blob = new Blob([JSON.stringify(entries, null, 2)], {
        type: "application/json",
      });
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = "selected_annotations.json";
      a.click();
      URL.revokeObjectURL(url);
    } catch (e) {
      console.error("Failed to download annotations", e);
      alert("Could not download selected annotations.");
    }
  };

  // ----------------- Render annotated text -----------------

  const renderAnnotatedText = () => {
    const text = uploadedText;
    if (!text) return null;
    if (!annotations.length) return text;

    const sorted = [...annotations].sort((a, b) => a.start - b.start);
    const chunks = [];
    let lastIndex = 0;

    for (const ann of sorted) {
      if (ann.start > lastIndex) {
        chunks.push({ type: "text", text: text.slice(lastIndex, ann.start) });
      }
      chunks.push({
        type: "ann",
        text: text.slice(ann.start, ann.end),
        label: ann.label,
      });
      lastIndex = ann.end;
    }

    if (lastIndex < text.length) {
      chunks.push({ type: "text", text: text.slice(lastIndex) });
    }

    return chunks.map((chunk, idx) => {
      if (chunk.type === "text") {
        return <span key={idx}>{chunk.text}</span>;
      }
      const bg = labels[chunk.label] || "#ffff99";
      return (
        <span
          key={idx}
          style={{
            backgroundColor: bg,
            padding: "1px 2px",
            borderRadius: "3px",
            margin: "0 1px",
            border: "1px solid #999",
          }}
          title={chunk.label}
        >
          {chunk.text}
        </span>
      );
    });
  };

  const labelNames = Object.keys(labels);

  const filteredDocuments = documents.filter((doc) => {
    if (!searchQuery.trim()) return true;
    const q = searchQuery.toLowerCase();
    return (
      doc.filename.toLowerCase().includes(q) ||
      (doc.preview || "").toLowerCase().includes(q)
    );
  });

  // ----------------- JSX -----------------

  return (
    <div
      style={{
        display: "flex",
        flexDirection: "row",
        minHeight: "100vh",
        fontFamily: "Inter, Arial, sans-serif",
        backgroundColor: "#f5f6fa",
        color: "#222",
      }}
    >
      {/* SIDEBAR */}
      <div
        style={{
          width: sidebarOpen ? "260px" : "70px",
          transition: "width 0.25s ease",
          background: "#ffffff",
          borderRight: "1px solid #e2e2e2",
          padding: "25px 10px",
          boxShadow: "2px 0 4px rgba(0,0,0,0.05)",
          display: "flex",
          flexDirection: "column",
          gap: "20px",
          position: "sticky",
          top: 0,
          height: "100vh",
          overflow: "hidden",
          whiteSpace: "nowrap",
        }}
      >
        <div
          style={{
            fontSize: "18px",
            fontWeight: "600",
            marginBottom: "10px",
            display: "flex",
            alignItems: "center",
            gap: "8px",
          }}
        >
          <span>🧬</span>
          <span
            style={{
              opacity: sidebarOpen ? 1 : 0,
              transition: "opacity 0.2s",
            }}
          >
            BioNLP
          </span>
        </div>

        <h2
          style={{
            fontSize: "16px",
            opacity: sidebarOpen ? 1 : 0,
            transition: "opacity 0.2s",
          }}
        >
          📂 Load Data
        </h2>

        <div style={{ display: "flex", flexDirection: "column", gap: "10px" }}>
          <label
            style={{
              cursor: "pointer",
              display: "flex",
              alignItems: "center",
              gap: "10px",
              fontSize: "14px",
            }}
          >
            <span>📝</span>
            <span
              style={{
                opacity: sidebarOpen ? 1 : 0,
                transition: "opacity 0.2s",
              }}
            >
              Paste text
            </span>
          </label>

          <label
            style={{
              cursor: "pointer",
              display: "flex",
              alignItems: "center",
              gap: "10px",
              fontSize: "14px",
            }}
          >
            <span>📄</span>
            <span
              style={{
                opacity: sidebarOpen ? 1 : 0,
                transition: "opacity 0.2s",
              }}
            >
              Upload file
            </span>
          </label>

          <label
            style={{
              cursor: "pointer",
              display: "flex",
              alignItems: "center",
              gap: "10px",
              fontSize: "14px",
            }}
          >
            <span>🗂️</span>
            <span
              style={{
                opacity: sidebarOpen ? 1 : 0,
                transition: "opacity 0.2s",
              }}
            >
              Upload folder
            </span>
          </label>

          <label
            style={{
              cursor: "pointer",
              display: "flex",
              alignItems: "center",
              gap: "10px",
              fontSize: "14px",
            }}
          >
            <span>🗜️</span>
            <span
              style={{
                opacity: sidebarOpen ? 1 : 0,
                transition: "opacity 0.2s",
              }}
            >
              Upload ZIP
            </span>
          </label>

          <label
            style={{
              cursor: "pointer",
              display: "flex",
              alignItems: "center",
              gap: "10px",
              fontSize: "14px",
            }}
          >
            <span>📁</span>
            <span
              style={{
                opacity: sidebarOpen ? 1 : 0,
                transition: "opacity 0.2s",
              }}
            >
              Documents
            </span>
          </label>
        </div>
      </div>

      {/* MAIN CONTENT */}
      <div
        style={{
          flex: 1,
          padding: "30px 40px",
          overflowY: "auto",
          transition: "margin-left 0.25s ease",
        }}
      >
        {/* Top Header */}
        <div
          style={{
            background: "white",
            padding: "16px 24px",
            borderRadius: "8px",
            boxShadow: "0 2px 4px rgba(0,0,0,0.06)",
            border: "1px solid #e3e3e3",
            display: "flex",
            alignItems: "center",
            gap: "12px",
            marginBottom: "25px",
          }}
        >
          <span style={{ fontSize: "28px" }}>🧬</span>
          <h1
            style={{
              margin: 0,
              fontSize: "24px",
              fontWeight: 700,
            }}
          >
            BioNLP Annotation Tool
          </h1>
          <button
            onClick={() => setSidebarOpen(!sidebarOpen)}
            style={{
              marginLeft: "auto",
              background: "none",
              border: "none",
              fontSize: "22px",
              cursor: "pointer",
            }}
            title="Toggle sidebar"
          >
            ☰
          </button>
        </div>

        {/* Backend status */}
        <div style={{ marginBottom: "20px" }}>
          <button
            onClick={testAPI}
            style={{
              padding: "8px 16px",
              background: "#2563eb",
              color: "white",
              borderRadius: "20px",
              border: "none",
              cursor: "pointer",
              fontWeight: 500,
            }}
          >
            Test Backend
          </button>
          <span style={{ marginLeft: "12px", fontSize: "14px" }}>{message}</span>
        </div>

        {/* Document Library (search + uploads + list) */}
        <div
          style={{
            background: "white",
            padding: "20px",
            borderRadius: "12px",
            maxWidth: "1100px",
            margin: "0 auto 30px auto",
            boxShadow: "0 2px 6px rgba(0,0,0,0.08)",
            border: "1px solid #e2e2e2",
          }}
        >
          <div
            style={{
              display: "flex",
              gap: "24px",
              alignItems: "flex-start",
              flexWrap: "wrap",
            }}
          >
            <div style={{ flex: "1 1 360px", minWidth: "320px" }}>
              <h2
                style={{
                  display: "flex",
                  alignItems: "center",
                  gap: "8px",
                  marginTop: 0,
                }}
              >
                📚 Document Library
              </h2>

              <div style={{ marginBottom: "10px" }}>
                <input
                  type="text"
                  placeholder="Search by filename or text..."
                  value={searchQuery}
                  onChange={(e) => setSearchQuery(e.target.value)}
                  style={{
                    width: "260px",
                    marginRight: "8px",
                    padding: "6px 8px",
                    borderRadius: "6px",
                    border: "1px solid #ccc",
                    fontSize: "14px",
                  }}
                />
                <button
                  style={{
                    padding: "6px 12px",
                    borderRadius: "6px",
                    border: "1px solid #ddd",
                    background: "#f3f4f6",
                    cursor: "pointer",
                  }}
                >
                  Search
                </button>
                <button
                  onClick={() => setSearchQuery("")}
                  style={{
                    padding: "6px 12px",
                    borderRadius: "6px",
                    border: "1px solid #ddd",
                    background: "#f9fafb",
                    cursor: "pointer",
                    marginLeft: "6px",
                  }}
                >
                  Clear
                </button>
              </div>

              <div
                style={{
                  display: "flex",
                  gap: "40px",
                  flexWrap: "wrap",
                  marginTop: "10px",
                }}
              >
                <div style={{ flex: "1 1 360px", minWidth: "280px" }}>
                  <h3>Upload Documents</h3>

                  <p>
                    <strong>Single file:</strong>{" "}
                    <input type="file" onChange={handleFileUpload} />
                  </p>

                  <p>
                    <strong>ZIP of files:</strong>{" "}
                    <input type="file" accept=".zip" onChange={handleZipUpload} />
                  </p>

                  <p>
                    <strong>Folder (multi-file):</strong>{" "}
                    <input
                      type="file"
                      multiple
                      webkitdirectory="true"
                      directory="true"
                      onChange={handleFolderUpload}
                    />
                  </p>

                  <div style={{ marginTop: "20px" }}>
                    <h3>Paste Text Manually</h3>

                    <input
                      type="text"
                      placeholder="Filename (optional)"
                      value={manualFilename}
                      onChange={(e) => setManualFilename(e.target.value)}
                      style={{
                        width: "260px",
                        marginBottom: "8px",
                        padding: "6px 8px",
                        borderRadius: "6px",
                        border: "1px solid #ccc",
                        fontSize: "14px",
                      }}
                    />

                    <br />

                    <textarea
                      placeholder="Paste or type text here..."
                      value={manualText}
                      onChange={(e) => setManualText(e.target.value)}
                      style={{
                        width: "100%",
                        height: "160px",
                        padding: "10px",
                        marginTop: "5px",
                        border: "1px solid #ccc",
                        borderRadius: "6px",
                        fontFamily: "monospace",
                        fontSize: "14px",
                        whiteSpace: "pre-wrap",
                      }}
                    />

                    <br />

                    <button
                      onClick={handleManualSubmit}
                      style={{
                        marginTop: "10px",
                        padding: "6px 12px",
                        borderRadius: "6px",
                        cursor: "pointer",
                        background: "#16a34a",
                        color: "white",
                        border: "none",
                        fontWeight: 500,
                      }}
                    >
                      Save Text as Document
                    </button>
                  </div>
                </div>
              </div>
            </div>

            <div
              style={{
                flex: "0 0 260px",
                minWidth: "240px",
                background: "white",
                border: "1px solid #e2e2e2",
                borderRadius: "12px",
                padding: "16px",
                boxShadow: "0 2px 6px rgba(0,0,0,0.08)",
              }}
            >
              <h3 style={{ marginTop: 0 }}>Documents</h3>
              {filteredDocuments.length === 0 ? (
                <p style={{ fontStyle: "italic" }}>No documents yet.</p>
              ) : (
                <ul
                  style={{
                    maxHeight: "400px",
                    overflow: "auto",
                    paddingLeft: 0,
                    margin: 0,
                  }}
                >
                  {filteredDocuments.map((doc) => (
                    <li
                      key={doc.doc_id}
                      style={{
                        marginBottom: "6px",
                        listStyle: "none",
                        fontSize: "14px",
                      }}
                    >
                      <div
                        style={{
                          display: "flex",
                          alignItems: "center",
                          gap: "6px",
                        }}
                      >
                        <input
                          type="checkbox"
                          checked={selectedDocs.includes(doc.doc_id)}
                          onChange={(e) => {
                            e.stopPropagation();
                            toggleDocSelection(doc.doc_id);
                          }}
                        />
                        <button
                          onClick={() => handleSelectDocument(doc.doc_id)}
                          style={{
                            border: "none",
                            background: "none",
                            textDecoration: "underline",
                            cursor: "pointer",
                            padding: 0,
                            fontWeight:
                              doc.doc_id === docId ? "bold" : "normal",
                            color: "#2563eb",
                          }}
                        >
                          {doc.filename}
                        </button>
                      </div>
                      <span style={{ fontSize: "11px", color: "#666" }}>
                        {" "}
                        – {doc.preview}
                      </span>
                    </li>
                  ))}
                </ul>
              )}
              <div
                style={{
                  marginTop: "12px",
                  display: "flex",
                  flexDirection: "column",
                  gap: "8px",
                }}
              >
                <button
                  onClick={downloadSelectedDocuments}
                  style={{
                    padding: "6px 10px",
                    borderRadius: "6px",
                    border: "1px solid #ddd",
                    background: "#f3f4f6",
                    cursor: "pointer",
                  }}
                >
                  Download Selected Documents (.json)
                </button>
                <button
                  onClick={downloadSelectedAnnotations}
                  style={{
                    padding: "6px 10px",
                    borderRadius: "6px",
                    border: "1px solid #ddd",
                    background: "#e0f2fe",
                    cursor: "pointer",
                  }}
                >
                  Download Selected Annotations (.json)
                </button>
              </div>
            </div>
          </div>
        </div>

        <div
          style={{
            display: "flex",
            flexWrap: "wrap",
            gap: "30px",
            alignItems: "flex-start",
          }}
        >
          <div style={{ flex: "1 1 700px", minWidth: "360px" }}>
            {/* Selected document + annotations */}
            {uploadedText && (
              <div
                style={{
                  background: "white",
                  padding: "20px",
                  borderRadius: "12px",
                  marginBottom: "30px",
                  boxShadow: "0 2px 6px rgba(0,0,0,0.08)",
                  border: "1px solid #e2e2e2",
                }}
              >
            <h2
              style={{
                display: "flex",
                alignItems: "center",
                gap: "8px",
                marginTop: 0,
              }}
            >
              📄 Document (select text to label)
            </h2>

            {docId && (
              <p style={{ fontSize: "12px", color: "#555" }}>
                Doc ID: <code>{docId}</code>
              </p>
            )}

            <div style={{ position: "relative" }}>
              <pre
                style={{
                  whiteSpace: "pre-wrap",
                  background: "#fff",
                  padding: "20px",
                  borderRadius: "8px",
                  border: "1px solid #ddd",
                  maxHeight: "500px",
                  overflow: "auto",
                  fontSize: "15px",
                  lineHeight: "1.5",
                }}
              >
                {renderAnnotatedText()}
              </pre>

              {popup.visible && popup.selection && labelNames.length > 0 && (
                <div
                id="annotation-popup"
                  style={{
                    position: "fixed",
                    top: popup.top,
                    left: popup.left,
                    background: "white",
                    border: "1px solid #ccc",
                    borderRadius: "6px",
                    padding: "8px",
                    boxShadow: "0 2px 6px rgba(0,0,0,0.2)",
                    zIndex: 9999,
                    fontSize: "12px",
                    maxWidth: "260px",
                    pointerEvents: "auto",
                  }}
                  ref={popupRef}
                >
                  <div style={{ marginBottom: "6px" }}>
    <label style={{ fontSize: "11px", marginRight: "4px" }}>
        Rank:
    </label>
    <input
        type="number"
        min="1"
        placeholder="1"
        value={popup.rank || ""}
        onChange={(e) =>
            setPopup({ ...popup, rank: e.target.value })
        }
        style={{
            width: "60px",
            padding: "4px",
            fontSize: "12px",
        }}
    />
</div>

                  <div
                    style={{
                      fontWeight: "bold",
                      marginBottom: "4px",
                    }}
                  >
                    Add annotation
                  </div>
                  <div
                    style={{
                      display: "flex",
                      flexWrap: "wrap",
                      gap: "4px",
                    }}
                  >
                    {labelNames.map((name) => (
                      <button
  key={name}
  onClick={() => handleLabelClick(name)}
  style={{
    fontSize: "11px",
    padding: "3px 8px",
    borderRadius: "999px",
    border: "1px solid #b7b7b7",
    background: labels[name] || "#ffff99",
    cursor: "pointer",
    color: "#000",
  }}
>
                        {name}
                      </button>
                    ))}
                  </div>
                  <div
                    style={{
                      marginTop: "6px",
                      fontStyle: "italic",
                      color: "#555",
                      maxHeight: "60px",
                      overflow: "hidden",
                    }}
                  >
                    “{popup.selection.text}”
                  </div>
                </div>
              )}
            </div>

            <h3 style={{ marginTop: "20px" }}>Annotations:</h3>
            {annotations.length === 0 ? (
              <p style={{ fontStyle: "italic" }}>
                No annotations yet. Select text and choose a label.
              </p>
            ) : (
              <ul>
                {annotations.map((ann, idx) => (
                  <li key={idx}>
                    <strong>{ann.label}</strong> — [{ann.start}, {ann.end}) — “
                    {ann.text}”
                  </li>
                ))}
              </ul>
            )}

            {/* Download buttons */}
            <div style={{ marginTop: "20px" }}>
              <h3>Download</h3>

              <button
                onClick={downloadAnnotatedText}
                style={{
                  padding: "8px 12px",
                  marginRight: "10px",
                  background: "#0284C7",
                  color: "white",
                  border: "none",
                  borderRadius: "6px",
                  cursor: "pointer",
                }}
              >
                Annotated Text (.txt)
              </button>

              <button
                onClick={downloadAnnotations}
                style={{
                  padding: "8px 12px",
                  marginRight: "10px",
                  background: "#10B981",
                  color: "white",
                  border: "none",
                  borderRadius: "6px",
                  cursor: "pointer",
                }}
              >
                Annotations (.json)
              </button>

              <button
                onClick={downloadWordDocument}
                style={{
                  padding: "8px 12px",
                  background: "#8B5CF6",
                  color: "white",
                  border: "none",
                  borderRadius: "6px",
                  cursor: "pointer",
                }}
              >
                Word (.docx)
              </button>
            </div>
          </div>
        )}

            {/* Label Manager */}
            <div
              style={{
                background: "white",
                padding: "20px",
                borderRadius: "12px",
                marginBottom: "30px",
                boxShadow: "0 2px 6px rgba(0,0,0,0.08)",
                border: "1px solid #e2e2e2",
              }}
            >
              <h2 style={{ marginTop: 0 }}>Label Manager</h2>

              <div style={{ display: "flex", gap: "10px", marginBottom: "10px" }}>
                <input
                  type="text"
                  placeholder="Label name"
                  value={newLabelName}
                  onChange={(e) => setNewLabelName(e.target.value)}
                  style={{
                    padding: "6px 8px",
                    borderRadius: "6px",
                    border: "1px solid #ccc",
                    fontSize: "14px",
                  }}
                />
                <input
                  type="text"
                  placeholder="#ffff99"
                  value={newLabelColor}
                  onChange={(e) => setNewLabelColor(e.target.value)}
                  style={{
                    padding: "6px 8px",
                    borderRadius: "6px",
                    border: "1px solid #ccc",
                    fontSize: "14px",
                  }}
                />
                <button
                  onClick={handleAddLabel}
                  style={{
                    padding: "6px 12px",
                    borderRadius: "6px",
                    cursor: "pointer",
                    background: "#2563eb",
                    color: "white",
                    border: "none",
                    fontWeight: 500,
                  }}
                >
                  Add / Update Label
                </button>
              </div>

              {labelNames.length === 0 ? (
                <p style={{ fontStyle: "italic" }}>No labels defined yet.</p>
              ) : (
                <ul style={{ paddingLeft: 0 }}>
                  {labelNames.map((name) => (
                    <li
                      key={name}
                      style={{
                        display: "flex",
                        alignItems: "center",
                        gap: "10px",
                        marginBottom: "6px",
                        listStyle: "none",
                      }}
                    >
                      <span
                        style={{
                          display: "inline-block",
                          width: "20px",
                          height: "12px",
                          marginRight: "6px",
                          background: labels[name],
                          border: "1px solid #333",
                        }}
                      ></span>
                      <div style={{ flex: 1 }}>
                        <strong>{name}</strong> — <code>{labels[name]}</code>
                      </div>
                      <button
                        onClick={() => handleDeleteLabel(name)}
                        style={{
                          border: "none",
                          background: "#fee2e2",
                          color: "#b91c1c",
                          borderRadius: "4px",
                          padding: "2px 6px",
                          cursor: "pointer",
                          fontSize: "12px",
                        }}
                      >
                        Delete
                      </button>
                    </li>
                  ))}
                </ul>
              )}
            </div>
          </div>

        </div>
      </div>
    </div>
  );
}

export default App;
