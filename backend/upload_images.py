import os
import requests
import json
import sys

def upload_folder(folder_path, scene_id, api_base_url="http://localhost:8000"):
    url = f"{api_base_url}/scene/{scene_id}/upload"
    
    if not os.path.isdir(folder_path):
        print(f"Error: Folder '{folder_path}' does not exist.")
        return

    # Find all image files
    valid_extensions = ('.png', '.jpg', '.jpeg', '.webp')
    image_files = [
        f for f in os.listdir(folder_path) 
        if f.lower().endswith(valid_extensions)
    ]
    
    if not image_files:
        print(f"No images found in '{folder_path}'.")
        return

    print(f"Found {len(image_files)} images in '{folder_path}'. Preparing upload...")
    
    # Open all files
    files_payload = []
    opened_files = []
    
    try:
        for filename in image_files:
            filepath = os.path.join(folder_path, filename)
            f = open(filepath, 'rb')
            opened_files.append(f)
            # FastAPI expects parameter name to match the API signature 'files'
            files_payload.append(('files', (filename, f, 'image/jpeg')))
        
        print(f"Sending POST request to {url}...")
        response = requests.post(url, files=files_payload)
        
        if response.status_code == 200:
            print("Successfully uploaded all images!")
            print("\nCopy the following 'photos' payload for your next API call:\n")
            print(json.dumps(response.json().get("photos_payload", []), indent=2))
        else:
            print(f"Upload failed with status code {response.status_code}:")
            print(response.text)
            
    finally:
        # Ensure all files are closed
        for f in opened_files:
            f.close()

if __name__ == "__main__":
    if len(sys.argv) < 3:
        print("Usage: python upload_images.py <path_to_images_folder> <scene_id> [api_base_url]")
        print("Example: python upload_images.py C:/my_photos house_123")
        sys.exit(1)
        
    folder = sys.argv[1]
    scene = sys.argv[2]
    base_url = sys.argv[3] if len(sys.argv) > 3 else "http://localhost:8000"
    
    upload_folder(folder, scene, base_url)
