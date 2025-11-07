# 💻 BioNLP Annotation App (Streamlit)

This project is a simple and interactive **Streamlit-based annotation tool** that allows users to load, view, and annotate medical or clinical notes easily. It was built to help streamline the annotation process for research projects, especially those related to medical text analysis and NLP.
 

## Overview

The app lets you upload text data from multiple sources, highlight important phrases or terms, assign labels, and export the annotations in a structured format.  
It’s meant to make manual annotation faster and more organized, with the flexibility to handle multiple files and different label types.


## Features

 1. Multiple ways to load data
- Paste text directly into the app  
- Upload `.txt`, `.csv`, or `.pdf` files  
- Upload a folder that contains multiple files (each file becomes a separate document to annotate)

 2. Highlight and annotate
- Select any portion of text to highlight and assign one or more labels  
- Labels appear in a popup when you select text  
- Each annotation is saved and displayed below the document for quick reference  
- Easy to add new label categories such as *Diagnosis*, *Medication*, *Symptom*, etc.

 3. Export annotations
- Download all annotations as **JSON** or **CSV**  
- Export includes document IDs, labeled text spans, and their corresponding label types  
- Works well with NLP pipelines and further data processing

4. Assistive features
- Frequently used labels appear first for quick access  
- Supports power labeling (you can apply multiple labels quickly)  
- User interface is clean, responsive, and designed for efficient use  
- Aiming to add more assistive options such as AI label suggestions in future updates


## How to Run

Clone the repository and install the required packages.

```bash
git clone https://github.com/raghuraavi99/annotation-app.git
cd annotation-app
python3 -m venv .venv
source .venv/bin/activate     # (Mac/Linux)
# For Windows: .venv\Scripts\activate
pip install -r requirements.txt
streamlit run app.py
http://localhost:8501
