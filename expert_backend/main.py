from fastapi import FastAPI, HTTPException, Body, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
import os
import subprocess
import sys
from expert_backend.services.network_service import network_service
from expert_backend.services.recommender_service import recommender_service

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Serve generated PDFs. 
# We mount the directory where PDFs are generated.
# Since the directory name is 'Overflow_Graph', we ensure it exists.
os.makedirs("Overflow_Graph", exist_ok=True)
app.mount("/results/pdf", StaticFiles(directory="Overflow_Graph"), name="pdfs")

class ConfigRequest(BaseModel):
    network_path: str
    action_file_path: str

class AnalysisRequest(BaseModel):
    disconnected_element: str

@app.post("/api/config")
def update_config(config: ConfigRequest):
    try:
        # Load network first to verify path and get branches
        network_service.load_network(config.network_path)
        # Update recommender config
        recommender_service.update_config(config.network_path, config.action_file_path)
        return {"status": "success", "message": "Configuration updated and network loaded"}
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

@app.get("/api/branches")
def get_branches():
    try:
        branches = network_service.get_disconnectable_elements()
        return {"branches": branches}
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

@app.get("/api/voltage-levels")
def get_voltage_levels():
    try:
        voltage_levels = network_service.get_voltage_levels()
        return {"voltage_levels": voltage_levels}
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

@app.get("/api/pick-path")
def pick_path(type: str = Query("file", enum=["file", "dir"])):
    """
    Opens a native OS file or directory picker and returns the selected path.
    Uses a subprocess to avoid tkinter/display issues in the main thread.
    """
    script = f"""
import tkinter as tk
from tkinter import filedialog
import sys

root = tk.Tk()
root.withdraw()
root.attributes('-topmost', True)
if "{type}" == "dir":
    path = filedialog.askdirectory()
else:
    path = filedialog.askopenfilename()
root.destroy()
if path:
    print(path)
"""
    try:
        # Run the script with the same python interpreter as the server
        result = subprocess.check_output([sys.executable, "-c", script], text=True).strip()
        return {"path": result if result else ""}
    except Exception as e:
        print(f"Error picking path: {e}")
        return {"path": "", "error": str(e)}

from fastapi.responses import StreamingResponse
import json

@app.post("/api/run-analysis")
async def run_analysis(request: AnalysisRequest):
    def event_generator():
        try:
            for event in recommender_service.run_analysis(request.disconnected_element):
                if event.get("pdf_path"):
                    filename = os.path.basename(event["pdf_path"])
                    event["pdf_url"] = f"/results/pdf/{filename}"
                
                # Yield JSON line
                yield json.dumps(event) + "\n"
        except Exception as e:
            yield json.dumps({"type": "error", "message": str(e)}) + "\n"

    return StreamingResponse(event_generator(), media_type="application/x-ndjson")

@app.get("/api/network-diagram")
def get_network_diagram():
    try:
        diagram = recommender_service.get_network_diagram()
        return diagram
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

@app.post("/api/n1-diagram")
def get_n1_diagram(request: AnalysisRequest):
    try:
        diagram = recommender_service.get_n1_diagram(request.disconnected_element)
        return diagram
    except Exception as e:
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=400, detail=str(e))

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
