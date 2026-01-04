# Tech Job Recommender

A smart job matching system for software engineers, data scientists, and DevOps folks. Enter your skills and preferences, get personalized job recommendations with clear explanations of why each job fits you.

## 🚀 Live Demo

| Component | URL |
|-----------|-----|
| **Frontend (Dashboard)** | [jobmatch-tech.streamlit.app](https://jobmatch-tech.streamlit.app/) |
| **Backend (API)** | [jobmatch-production-0420.up.railway.app](https://jobmatch-production-0420.up.railway.app/) |
| **API Docs** | [jobmatch-production-0420.up.railway.app/docs](https://jobmatch-production-0420.up.railway.app/docs) |

## What It Does

- Matches your skills against 2,600+ real tech jobs from LinkedIn
- Shows you exactly why each job is a good (or not so good) fit
- Lets you adjust what matters most: skills, salary, remote work, experience level
- Gives you skill gap analysis so you know what to learn next

## Tech Stack

- **Frontend**: Streamlit, Plotly
- **Backend**: FastAPI, SQLite
- **ML**: Sentence-Transformers, Qdrant
- **LLM**: Groq (Llama 3)


## Quick Start

### 1. Clone and Install

```bash
git clone https://github.com/your-repo/job-recommender.git
cd job-recommender
pip install -r requirements.txt
```

### 2. Set Up Your API Key

You need a free Groq API key for the LLM features. Get one at [console.groq.com](https://console.groq.com/keys).

```bash
cp .env.example .env
# Edit .env and add your GROQ_API_KEY
```

### 3. Download Job Data

```bash
# Set up Kaggle credentials first (see below)
python -m scripts.download_kaggle_data --dataset linkedin
python -m scripts.ingest_data --kaggle data/kaggle/linkedin/postings.csv --limit 50000
```

### 4. Generate Embeddings

```bash
python -m scripts.generate_embeddings
python -m scripts.index_embeddings
```

### 5. Run the App

```bash
# Start the dashboard
streamlit run streamlit_app/app.py
```

Open http://localhost:8501 in your browser.

## How It Works

```
Your Profile → Ranking Engine → Recommendations
     ↓              ↓                  ↓
  Skills      Weighted Scoring    Explanations
  Experience  Skill Matching      Skill Gaps
  Salary      Location Match      Match Scores
```

The system uses:
- **Sentence Transformers** for understanding job descriptions
- **Qdrant** for fast similarity search
- **Groq/Llama** for extracting requirements from job posts
- **Weighted scoring** across 5 dimensions: skills, experience, seniority, location, salary

## Weight Presets

Pick a preset that matches your job search priorities:

| Preset | Focus |
|--------|-------|
| Skill-Focused | Best skill match (50% weight on skills) |
| Career Growth | Experience alignment (35% on experience) |
| Compensation First | Salary fit (35% on salary) |
| Remote Priority | Location/remote (30% on location) |
| Balanced | Equal consideration of everything |

Or set your own custom weights.

## Project Structure

```
├── src/                    # Core logic
│   ├── ranking.py          # Job scoring and ranking
│   ├── recommendation.py   # Explanation generation
│   ├── embedding.py        # Text embeddings
│   ├── database.py         # SQLite storage
│   └── vector_store.py     # Qdrant integration
├── streamlit_app/          # Web dashboard
├── scripts/                # Data pipeline
└── tests/                  # Unit and property tests
```

## API Endpoints

If you want to use the REST API directly:

```bash
# Start the API server
uvicorn src.api.main:app --port 8000
```

| Endpoint | Description |
|----------|-------------|
| `POST /api/candidates` | Create a candidate profile |
| `GET /api/recommendations/{id}` | Get job recommendations |
| `GET /api/jobs` | List all jobs |
| `PUT /api/weights/{id}` | Update ranking weights |
| `POST /api/feedback` | Submit like/dislike feedback |

API docs at http://localhost:8000/docs

## Setting Up Kaggle

To download the LinkedIn job dataset:

1. Create account at [kaggle.com](https://kaggle.com)
2. Go to Settings → API → Create New Token
3. Save `kaggle.json` to `~/.kaggle/` (Linux/Mac) or `%USERPROFILE%\.kaggle\` (Windows)
4. Run `python -m scripts.download_kaggle_data --check`


## Tech Stack

- **Frontend**: Streamlit, Plotly
- **Backend**: FastAPI, SQLite
- **ML**: Sentence-Transformers, Qdrant
- **LLM**: Groq (Llama 3)


## Deployment

This project uses a split deployment:
- **Backend (API)**: Railway - [jobmatch-production-0420.up.railway.app](https://jobmatch-production-0420.up.railway.app/)
- **Frontend (Dashboard)**: Streamlit Cloud - [jobmatch-tech.streamlit.app](https://jobmatch-tech.streamlit.app/)

### Step 1: Deploy Backend to Railway

1. Push your code to GitHub

2. Go to [railway.app](https://railway.app) and sign in with GitHub

3. Click "New Project" → "Deploy from GitHub repo"

4. Select your repository

5. Add environment variable: `GROQ_API_KEY`

6. Railway will build using the Dockerfile and deploy

7. Copy your Railway URL (e.g., `https://your-app.railway.app`)

### Step 2: Deploy Frontend to Streamlit Cloud

1. Go to [share.streamlit.io](https://share.streamlit.io)

2. Sign in with GitHub

3. Click "New app" and select your repository

4. Set these options:
   - Main file path: `streamlit_app/app.py`
   - Python version: 3.11

5. Add secret in "Advanced settings" → "Secrets":
   ```toml
   API_BASE_URL = "https://your-app.railway.app"
   ```

6. Click "Deploy"

Your frontend will be live at `https://your-app.streamlit.app`
