from fastapi import APIRouter, HTTPException, BackgroundTasks, UploadFile, File, Form
from pydantic import BaseModel
from typing import List, Dict, Any, Optional
import os
import shutil
from app.services.director import DirectorService
from app.schemas.remotion import AudioConfig, BrandingConfig, RemotionInputProps
from app.worker.tasks import render_video_task

router = APIRouter()

class SceneVideoRequest(BaseModel):
    photos: List[Dict[str, Any]]
    tour_type: str = "PROPERTY_SHOWCASE"
    pacing_speed: str = "NORMAL"
    audio: AudioConfig
    branding: BrandingConfig

@router.post("/scene/{scene_id}/video", response_model=Dict[str, Any])
async def create_scene_video(scene_id: str, request: SceneVideoRequest):
    try:
        # Initialize the director engine
        director = DirectorService(tour_type=request.tour_type, pacing_speed=request.pacing_speed)
        
        # Build the payload
        payload = director.build_director_script(
            photos=request.photos,
            audio=request.audio,
            branding=request.branding
        )
        
        payload_dict = payload.model_dump()
        output_filename = f"output_{scene_id}.mp4"
        
        # Send to Celery worker
        task = render_video_task.delay(payload_dict, output_filename)
        
        return {
            "message": "Video rendering started",
            "scene_id": scene_id,
            "task_id": task.id,
            "output_filename": output_filename
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/scene/{scene_id}/upload")
async def upload_scene_images(scene_id: str, files: List[UploadFile] = File(...)):
    """
    Helper endpoint to upload local images for testing.
    Returns a list of payload objects you can pass into the /video endpoint.
    """
    upload_dir = os.path.join("uploads", scene_id)
    os.makedirs(upload_dir, exist_ok=True)
    
    uploaded_photos = []
    
    for file in files:
        file_path = os.path.join(upload_dir, file.filename)
        with open(file_path, "wb") as buffer:
            shutil.copyfileobj(file.file, buffer)
            
        # Return the local URL that FastAPI is hosting
        local_url = f"http://localhost:8000/uploads/{scene_id}/{file.filename}"
        
        # We assign a default room_type, but you can change this in the JSON payload later
        uploaded_photos.append({
            "image_url": local_url,
            "room_type": "Other" 
        })
        
    return {
        "message": f"Successfully uploaded {len(files)} images.",
        "photos_payload": uploaded_photos
    }
