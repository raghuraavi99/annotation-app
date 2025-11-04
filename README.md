# 🩺 Medical Notes Annotation App (Streamlit)

A simple and reusable **annotation tool** built with **Streamlit** to help researchers quickly annotate text data — especially medical or clinical notes.  
This tool allows users to highlight terms, assign labels (e.g., Diagnosis, Symptom, Medication), and export annotations in structured formats.

---

## 🚀 Features

- 📂 Upload or paste text notes (`.txt` or `.csv`)
- 🧠 Highlight and tag key phrases using search or character indices
- 🏷️ Custom label management (Diagnosis, Symptom, Medication, etc.)
- 💾 Export annotations as **JSONL** or **CSV**
- 🔁 Multi-document workspace for batch annotation
- 🧩 Built for **reusability** and **future extensions**

---

## 🧰 Tech Stack

- **Framework:** Streamlit  
- **Language:** Python 3  
- **Libraries:** Pandas, Streamlit  
- **Export formats:** JSONL, CSV  

---

## 🖥️ How to Run Locally

### 1️⃣ Clone this repo
```bash
git clone https://github.com/raghuraavi99/annotation-app.git
cd annotation-app
2️⃣ Create a virtual environment
python3 -m venv .venv
source .venv/bin/activate
3️⃣ Install dependencies
pip install -r requirements.txt
4️⃣ Run the app
streamlit run app.py

http://localhost:8501
