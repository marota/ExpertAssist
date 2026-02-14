# CLAUDE.md - ExpertAssist

## Project Overview

ExpertAssist is a full-stack web application for **power grid contingency analysis and N-1 planning**. It provides an interface to the `expert_op4grid_recommender` library, allowing operators to simulate element disconnections, visualize network overflow graphs, and receive prioritized remedial action recommendations.

## Architecture

**Monorepo** with two main components:

```
ExpertAssist/
├── expert_backend/          # Python FastAPI backend
│   ├── main.py              # FastAPI app, API endpoints, CORS config
│   └── services/
│       ├── network_service.py       # pypowsybl network loading & queries
│       └── recommender_service.py   # Analysis orchestration, PDF/SVG generation
├── frontend/                # React + TypeScript + Vite frontend
│   └── src/
│       ├── App.tsx           # Root component (layout: header, config, action feed, viz)
│       ├── api.ts            # Axios HTTP client (base URL: localhost:8000)
│       ├── types.ts          # TypeScript interfaces
│       └── components/
│           ├── ConfigurationPanel.tsx  # Network/action path inputs, branch selector
│           ├── ActionFeed.tsx          # Prioritized action results display
│           └── VisualizationPanel.tsx  # PDF viewer (iframe)
├── Overflow_Graph/          # Generated PDFs (created at runtime)
├── standalone_interface.html # Self-contained HTML version of the UI
└── test_*.py / verify_*.py  # Root-level integration test scripts
```

## Tech Stack

### Backend
- **Python** with **FastAPI** + **Uvicorn**
- **pypowsybl** - Power system network loading, load flow, and diagram generation
- **expert_op4grid_recommender** - Domain-specific grid optimization recommendations
- **grid2op** / **pandapower** / **lightsim2grid** - Grid simulation backends

### Frontend
- **React 19** with **TypeScript 5.9**
- **Vite 7** - Build tool and dev server
- **axios** - HTTP client
- **react-select** - Searchable dropdown for branch selection
- **react-zoom-pan-pinch** - Pan/zoom for visualizations
- **framer-motion** - Animations
- **lucide-react** - Icons

## Development Workflow

### Running the Backend

```bash
# From the project root:
python -m expert_backend.main
# Or:
uvicorn expert_backend.main:app --host 0.0.0.0 --port 8000
```

The backend serves on `http://localhost:8000`. It expects `pypowsybl` and `expert_op4grid_recommender` to be available in the Python environment.

### Running the Frontend

```bash
cd frontend
npm install
npm run dev      # Start Vite dev server with HMR
```

The frontend dev server proxies API calls to `http://localhost:8000` (hardcoded in `frontend/src/api.ts`).

### Build & Lint

```bash
cd frontend
npm run build    # TypeScript compilation (tsc -b) + Vite production build
npm run lint     # ESLint
npm run preview  # Preview production build
```

### Running Tests

Tests are integration tests that require a running backend with valid data paths:

```bash
# Start the backend first, then:
python test_backend.py         # Config, branches, and analysis tests
python test_api_stream.py      # Streaming response tests
python test_n1_api.py          # N-1 contingency diagram tests
python test_voltage_api.py     # Voltage levels API tests
python verify_n1_simulation.py # N-1 simulation verification
```

There is no unit test framework or automated test runner configured.

## API Endpoints

| Method | Path | Description |
|--------|------|-------------|
| POST | `/api/config` | Set network path and action file path |
| GET | `/api/branches` | List disconnectable elements (lines + transformers) |
| GET | `/api/voltage-levels` | List voltage levels in the network |
| POST | `/api/run-analysis` | Run N-1 contingency analysis (streaming NDJSON response) |
| GET | `/api/network-diagram` | Get full network SVG diagram |
| POST | `/api/n1-diagram` | Get post-contingency network SVG diagram |
| GET | `/api/pick-path` | Open native OS file/directory picker (tkinter subprocess) |
| GET | `/results/pdf/{filename}` | Serve generated PDF files from `Overflow_Graph/` |

## Key Patterns & Conventions

### Backend
- **Singleton services**: `network_service` and `recommender_service` are module-level singleton instances
- **Streaming responses**: Analysis uses `StreamingResponse` with NDJSON (`application/x-ndjson`), yielding `{"type": "pdf", ...}` then `{"type": "result", ...}` events
- **AC/DC fallback**: Analysis first tries AC load flow; falls back to DC if AC does not converge
- **Threaded analysis**: `run_analysis` runs the computation in a background thread and polls for PDF generation
- **JSON sanitization**: NumPy types are recursively converted to native Python types via `sanitize_for_json()`
- **No formal Python linter config**: Code follows PEP 8 conventions manually

### Frontend
- **Strict TypeScript**: `strict: true`, `noUnusedLocals`, `noUnusedParameters`, `noFallthroughCasesInSwitch`
- **Functional components** with React hooks; no external state management library
- **Inline styles**: Components use inline `style` objects rather than CSS modules or utility classes
- **Props-based data flow**: State lifted to `App.tsx`, passed down via props
- **ESLint**: Flat config (v9+) with `typescript-eslint`, `react-hooks`, and `react-refresh` plugins

### Data Flow
1. User sets network path + action file path -> `POST /api/config` loads the network
2. Frontend fetches disconnectable branches -> `GET /api/branches`
3. User selects a branch and runs analysis -> `POST /api/run-analysis`
4. Backend streams events: first a PDF event (overflow graph), then the result with enriched actions
5. Frontend displays the PDF in an iframe and the actions in the ActionFeed panel

## Dependencies

### Backend (`expert_backend/requirements.txt` + `overrides.txt`)
- `fastapi`, `uvicorn`, `python-multipart`
- `pypowsybl`, `expert_op4grid_recommender` (expected in venv)
- `pandas>=2.2.2`, `numpy>=2.0.0`, `grid2op>=1.12.2`, `pandapower>=2.14.0`
- `lightsim2grid>=0.12.0`, `matplotlib>=3.10.6`, `scipy>=1.16.0`
- `lxml>=6.0.0`, `contourpy>=1.2.0`, `tqdm>=4.65.0`

### Frontend (`frontend/package.json`)
- See `dependencies` and `devDependencies` in `frontend/package.json`

## File Conventions

- Network data files: `.xiidm` format (loaded by pypowsybl)
- Action definitions: `.json` files with action IDs mapping to descriptions
- Generated outputs: PDF files in `Overflow_Graph/` directory
- Network layouts: `grid_layout.json` (node ID -> [x, y] coordinates)

## Notes for AI Assistants

- The backend API base URL is hardcoded to `http://localhost:8000` in `frontend/src/api.ts`
- CORS is configured to allow all origins (`allow_origins=["*"]`)
- The `ConfigurationPanel` has hardcoded default paths specific to a developer workstation; these are not portable
- There is no CI/CD pipeline, Dockerfile, or containerization configured
- There is no root-level `.gitignore`; only `frontend/.gitignore` exists
- Root-level Python scripts (`test_*.py`, `reproduce_error.py`, `repro_stuck.py`, `fix_zoom.py`, `inspect_metadata.py`) are ad-hoc development/debugging utilities, not part of the main application
- The `standalone_interface.html` is a self-contained version of the full UI in a single HTML file
