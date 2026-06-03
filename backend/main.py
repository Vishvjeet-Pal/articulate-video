import os
import uvicorn
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from app.api.endpoints import scene

from fastapi.middleware.cors import CORSMiddleware

# Create uploads directory if it doesn't exist
os.makedirs("uploads", exist_ok=True)

app = FastAPI(title="Articulait Video Engine")

# Configure CORS so Remotion WebGL loader can load images cross-origin
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Mount the uploads directory so Remotion can access the images via URL
app.mount("/uploads", StaticFiles(directory="uploads"), name="uploads")

app.include_router(scene.router)

if __name__ == "__main__":
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)
