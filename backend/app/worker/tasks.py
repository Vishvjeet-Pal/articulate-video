import os
import json
import subprocess
from celery import Celery
from celery.utils.log import get_task_logger
from app.core.config import CELERY_BROKER_URL, CELERY_RESULT_BACKEND

logger = get_task_logger(__name__)

celery_app = Celery(
    "articulait_worker",
    broker=CELERY_BROKER_URL,
    backend=CELERY_RESULT_BACKEND
)

@celery_app.task(bind=True)
def render_video_task(self, payload_dict: dict, output_filename: str):
    """
    Writes the payload to a temp JSON file and executes local npx remotion render.
    """
    import tempfile
    
    with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as temp_json:
        json.dump(payload_dict, temp_json)
        temp_json_path = temp_json.name
    
    # Path to remotion project root, assuming sibling directory
    remotion_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "../../../remotion"))
    
    # Ensure absolute path for output
    out_path = os.path.abspath(output_filename)
    
    npx_cmd = "npx.cmd" if os.name == "nt" else "npx"
    cmd = [
        npx_cmd, "remotion", "render",
        "CinematicTour", # The composition ID
        out_path,
        "--props", temp_json_path
    ]
    
    try:
        logger.info(f"Starting Remotion render for composition 'CinematicTour'. Output: {out_path}")
        
        # Run remotion local CLI rendering with real-time log streaming
        process = subprocess.Popen(
            cmd,
            cwd=remotion_dir,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            encoding="utf-8",
            bufsize=1
        )
        
        output_lines = []
        for line in iter(process.stdout.readline, ""):
            clean_line = line.strip()
            if clean_line:
                logger.info(f"[Remotion] {clean_line}")
                output_lines.append(clean_line)
                
        return_code = process.wait()
        if return_code != 0:
            error_msg = "\n".join(output_lines)
            logger.error(f"Remotion render failed with exit code {return_code}")
            return {"status": "error", "message": error_msg}
            
        logger.info(f"Remotion render completed successfully: {out_path}")
        return {"status": "success", "master_video": out_path}
    except Exception as e:
        logger.error(f"Error during video rendering task execution: {str(e)}")
        return {"status": "error", "message": str(e)}
    finally:
        if os.path.exists(temp_json_path):
            os.remove(temp_json_path)

@celery_app.task
def generate_social_derivatives_task(master_video_path: str, crops: dict):
    """
    Uses FFmpeg to crop the master video for social derivatives based on saliency data.
    crops = {"IG_REELS": "1080:1920:420:0", "FB_FEED": "1080:1080:420:420"}
    """
    logger.info(f"Starting social derivatives generation for: {master_video_path}")
    results = {}
    base_name = os.path.splitext(master_video_path)[0]
    # Path to remotion project root, assuming sibling directory
    remotion_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "../../../remotion"))
    npx_cmd = "npx.cmd" if os.name == "nt" else "npx"
    
    for platform, crop_str in crops.items():
        out_path = f"{base_name}_{platform}.mp4"
        cmd = [
            npx_cmd, "remotion", "ffmpeg", "-y", "-i", master_video_path,
            "-vf", f"crop={crop_str}",
            "-c:a", "copy",
            out_path
        ]
        
        logger.info(f"Executing crop command for {platform}...")
        try:
            process = subprocess.Popen(
                cmd,
                cwd=remotion_dir,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                encoding="utf-8",
                bufsize=1
            )
            
            for line in iter(process.stdout.readline, ""):
                clean_line = line.strip()
                if clean_line:
                    logger.info(f"[FFmpeg-{platform}] {clean_line}")
                    
            return_code = process.wait()
            if return_code == 0:
                logger.info(f"Successfully generated derivative for {platform} at {out_path}")
                results[platform] = out_path
            else:
                logger.error(f"FFmpeg cropping failed for {platform} with exit code {return_code}")
                results[platform] = {"error": f"FFmpeg failed with exit code {return_code}"}
        except Exception as e:
            logger.error(f"Exception during cropping for {platform}: {str(e)}")
            results[platform] = {"error": str(e)}
            
    logger.info("Social derivatives generation task complete.")
    return results
