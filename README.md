<div align="center">
  <h1 align="center">DataForge</h1>
  <p align="center">
    <strong>A Universal Multimodal AI Dataset Extraction & Synthesis Engine</strong>
  </p>
</div>

<br />

## 🪐 Welcome to DataForge

**DataForge** is a high-performance, modular system designed to aggressively scrape, clean, synthesize, and package raw web data into clean datasets. Supported across four dominant data modalities—**Textual, Audio, Imagery, and Relational Graphs**—DataForge operates alongside advanced NLP semantic evaluators and computer vision heuristics to filter out noise, leaving you with pure, highly-correlated data schemas packaged for ML training flows.

---

## ⚡ Core Features

### 1. 🗃️ Universal Multimodal Extraction
DataForge orchestrates distributed scraping pipelines tailored to distinct modalities:
- **Text & NLP Datasets:** Mines paragraphs, applies precise NLP TF-IDF cosine similarity scoring, and cleanses data down to strictly aligned contexts.
- **Audio & Spectrogram Generation:** Leverages deep STT (Speech-to-Text) inference to evaluate MP3/WAV/OGG captures locally. Computes visual spectrograms using `ffmpeg` & `pydub`.
- **Image CNN Assets:** Harvests images based on localized captions and generates semantic entity tags. Features an interactive UI to modify scale, format, and aspect ratios.
- **Relational Graph Generation:** Constructs deep nodes and edge hierarchies mapped dynamically via `networkx` to package rich associative knowledge graphs.

### 2. 🛡️ Advanced Semantic Curation
Instead of blind ingestion, DataForge runs a stringent contextual refinement loop. The platform translates data, determines relevance confidence levels, enforces semantic tagging, and aggressively culls irrelevant anomalies from your dataset before packaging in `.json` or `.csv`. 

### 3. 🎨 Dark Mode Cyber-UI
Built on Next.js, the frontend leverages a beautiful, dynamic, glassmorphic UI. 
- Real-time **Data Stream** virtualization.
- Highly actionable **ZIP Export Pipelines** uniquely sculpted per modality (e.g., dynamic sliders for image dimensions or toggle panes for raw vs. spectrogram Audio generation).
- Beautiful micro-animations and glowing indicators mapping background pipeline latency.

---

## 💻 Tech Stack

**Frontend Framework:** 
- Next.js (TypeScript)
- TailwindCSS
- Lucide React (Icons)

**Backend Architecture:**
- FastAPI / Uvicorn Python Server
- ThreadPoolExecutor Concurrency
- `BeautifulSoup4` & `Requests` 

**AI / Processing Dependencies:**
- `scikit-learn` & `NLTK` (Text Semantics)
- `SpeechRecognition` & `pydub` + `ffmpeg` (Audio/Spectrograms)
- `NetworkX` (Graph Analytics)

---

## 🚀 Installation & Setup

Before building DataForge locally, make sure you have `Node.js`, `Python 3.10+`, and system dependencies (`ffmpeg`) installed for multimodal handling.

### macOS Prerequisites
```bash
# Required for Audio Spectrogram pipelines
brew install ffmpeg
```

### Backend Initialization (Python / FastAPI)
```bash
cd backend
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt

# Start the DataForge FastAPI Server
python -m uvicorn main:app --reload --port 8000
```

### Frontend Initialization (Next.js)
Open a new terminal session.
```bash
cd frontend
npm install

# Start the user interface
npm run dev
```

The UI will automatically bind to `http://localhost:3000`. 

---

## 🏎️ Quick Start Workflow

1. **Launch a Forge:** Type in your context/target topic in the main input field.
2. **Select Modality:** Pick Text, Audio, Knowledge Graph, or Image.
3. **Refine Sources:** Select the specific source repositories DataForge will infiltrate.
4. **Data Stream:** Watch the background parser index, evaluate, and dynamically drop/retain data based on relevance matching algorithms.
5. **Download Batch ZIP:** Depending on the modality, dial in your configurations (i.e., Spectrogram vs Raw Audio, or CSV vs JSON indexes) and download the perfectly structured archive direct to your machine. 

---

<div align="center">
  <p>Built for automated intelligence.</p>
</div>
