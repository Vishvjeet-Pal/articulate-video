import redis
import json
import sys

r = redis.Redis(host="localhost", port=6379, db=0)
task_id = "d2fdf62b-5a89-4e22-8f4c-e4374547671a"
key = f"celery-task-meta-{task_id}"

val = r.get(key)
if val:
    try:
        data = json.loads(val)
        with open("task_meta.json", "w", encoding="utf-8") as f:
            json.dump(data, f, indent=4)
        print("Successfully wrote metadata to task_meta.json")
    except Exception as e:
        print(f"Error parsing json: {e}")
else:
    print("Key not found in Redis.")
