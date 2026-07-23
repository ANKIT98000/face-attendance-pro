import os
import boto3
from fastapi import APIRouter, UploadFile, File, Form, Request, BackgroundTasks
import cv2
import numpy as np
import face_recognition
from database import get_db_connection
from dotenv import load_dotenv

load_dotenv()
RESIZE_WIDTH = 600
BUCKET_NAME = os.getenv("S3_BUCKET_NAME")

# Initialize AWS S3 Client
s3_client = boto3.client(
    's3',
    aws_access_key_id=os.getenv("AWS_ACCESS_KEY_ID"),
    aws_secret_access_key=os.getenv("AWS_SECRET_ACCESS_KEY"),
    region_name=os.getenv("AWS_REGION")
)

router = APIRouter()

def background_training(employee_id: str, name: str, encodings_list: list, raw_files: list, filenames: list):
    print(f"\n{'-'*50}")
    print(f"[BACKGROUND] Saving AI spatial features for ID: {employee_id}...")

    # Calculate the mean encoding directly (since the array is already processed)
    master_encoding = np.mean(encodings_list, axis=0).tolist()

    # Step 2: Persist master encoding to Vector Database
    try:
        conn = get_db_connection()
        if conn is not None:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO employees (employee_id, name, status, training_status, face_encoding) 
                VALUES (%s, %s, 'ACTIVE', 'TRAINED', %s)
                ON CONFLICT (employee_id) DO UPDATE 
                SET name = EXCLUDED.name, training_status = 'TRAINED', face_encoding = EXCLUDED.face_encoding
            """, (employee_id, name, str(master_encoding)))
            conn.commit()
            cursor.close()
            conn.close()
            print(f"[SUCCESS] AI biometric profile securely saved to Vector Database.")
    except Exception as e:
        print(f"[ERROR] Database execution failed: {e}")

    # Step 3: Upload original assets to S3 Storage
    print(f"[BACKGROUND] Initializing S3 upload to bucket: {BUCKET_NAME}...")
    try:
        for i, file_content in enumerate(raw_files):
            # Target path structure: register/{employee_id}/{filename}
            file_key = f"register/{employee_id}/{filenames[i]}"
            s3_client.put_object(Bucket=BUCKET_NAME, Key=file_key, Body=file_content, ContentType='image/jpeg')
        print("[SUCCESS] Registration assets successfully synchronized with Cloud Storage.")
    except Exception as e:
        print(f"[ERROR] S3 synchronization failed: {e}")
        
    print(f"{'-'*50}\n")

@router.post("/register")
async def register_employee(
    request: Request, 
    background_tasks: BackgroundTasks, 
    employee_id: str = Form(default=None),
    name: str = Form(default=None),
    file0: UploadFile = File(default=None), 
    file1: UploadFile = File(default=None),
    file2: UploadFile = File(default=None)
):
    print(f"\n{'-'*50}")
    print("[INFO] Incoming API Request: /register (Memory + S3 Routine)")

    if not employee_id or not name or not file0 or not file1 or not file2:
        return {"success": False, "msg": "Invalid request. Missing required parameters or image payloads."}

    files = [file0, file1, file2]
    encodings_list, raw_files, filenames = [], [], []

    print("[INFO] Validating and optimizing image payloads in memory...")
    for i, f in enumerate(files):
        file_content = await f.read()
        
        raw_files.append(file_content)
        filenames.append(f.filename)

        nparr = np.frombuffer(file_content, np.uint8)
        img = cv2.imdecode(nparr, cv2.IMREAD_COLOR)

        if img is None:
            return {"success": False, "msg": f"Data corruption detected in payload: file{i}."}

        # Dynamic downscaling for optimized inference speed
        height, width = img.shape[:2]
        if width > RESIZE_WIDTH:
            img = cv2.resize(img, (RESIZE_WIDTH, int(height * (RESIZE_WIDTH / width))))

        rgb_frame = cv2.cvtColor(img, cv2.COLOR_BGR2RGB)
        face_locations = face_recognition.face_locations(rgb_frame)
        
        if not face_locations or len(face_locations) > 1: 
            return {"success": False, "msg": f"Facial detection failed for file{i}. Ensure a single, clearly visible face."}

        # Extract 128-d face encoding immediately
        current_encoding = face_recognition.face_encodings(rgb_frame, face_locations)[0]

        # Security Lock: Compare 2nd and 3rd photo with the 1st photo (index 0)
        if i > 0:
            is_match = face_recognition.compare_faces([encodings_list[0]], current_encoding, tolerance=0.6)[0]
            if not is_match:
                print(f"[WARNING] Identity mismatch detected in file{i}!")
                return {"success": False, "msg": "Security Alert: All 3 photos must belong to the exact same person."}

        # If it's a match, append to the list
        encodings_list.append(current_encoding)

    # Offload heavy computation and I/O operations to background workers
    background_tasks.add_task(background_training, employee_id, name, encodings_list, raw_files, filenames)   
    
    print("[INFO] Validation successful. Returning immediate response to client.")
    print(f"{'-'*50}")
    return {"success": True, "msg": "Registration payload accepted for processing."}