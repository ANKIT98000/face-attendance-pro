import os
import boto3
from fastapi import APIRouter, UploadFile, File, Form, Request, BackgroundTasks
import cv2
import numpy as np
import face_recognition
from database import get_db_connection
from datetime import datetime
from dotenv import load_dotenv

load_dotenv()
MATCH_THRESHOLD = 0.45
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

def background_s3_upload(employee_id: str, file_content: bytes, is_match: bool):
    """Handles asynchronous upload of verification attempts to Cloud Storage."""
    now = datetime.now()
    date_folder = now.strftime("%Y-%m-%d")
    time_str = now.strftime("%H%M%S")
    
    status = "success" if is_match else "failed"
    
    # Target path structure: verify/{employee_id}/YYYY-MM-DD/status_HHMMSS.jpg
    file_key = f"verify/{employee_id}/{date_folder}/{status}_{time_str}.jpg"
    
    try:
        s3_client.put_object(Bucket=BUCKET_NAME, Key=file_key, Body=file_content, ContentType='image/jpeg')
        print(f"[BACKGROUND] Verification attempt securely archived at: {file_key}")
    except Exception as e:
        print(f"[ERROR] S3 archival failed: {e}")

@router.post("/verify_face")
async def verify_face(
    request: Request, 
    background_tasks: BackgroundTasks,
    employee_id: str = Form(default=None),
    file: UploadFile = File(default=None)
):
    print(f"\n{'-'*50}")
    print("[INFO] Incoming API Request: /verify_face (Vector Match Routine)")

    if not employee_id or not file:
        return {"success": False, "msg": "Invalid request. Missing ID or image payload."}

    contents = await file.read()
    nparr = np.frombuffer(contents, np.uint8)
    img = cv2.imdecode(nparr, cv2.IMREAD_COLOR)

    if img is None:
        return {"success": False, "msg": "Data corruption detected in image payload."}

    # Dynamic downscaling for optimized inference speed
    height, width = img.shape[:2]
    if width > RESIZE_WIDTH:
        img = cv2.resize(img, (RESIZE_WIDTH, int(height * (RESIZE_WIDTH / width))))

    rgb_frame = cv2.cvtColor(img, cv2.COLOR_BGR2RGB)
    face_locations = face_recognition.face_locations(rgb_frame)
    
    if not face_locations: 
        return {"success": False, "msg": "Verification failed: No face detected in the frame."}
    if len(face_locations) > 1: 
        return {"success": False, "msg": "Verification failed: Multiple faces detected. Ensure a single subject."}
        
    incoming_encodings = face_recognition.face_encodings(rgb_frame, face_locations)
    if not incoming_encodings:
        return {"success": False, "msg": "Verification failed: Facial features lack clarity."}

    incoming_vector = incoming_encodings[0].tolist()

    # Database Vector Distance Calculation (pgvector)
    try:
        conn = get_db_connection()
        if conn is None:
             return {"success": False, "msg": "Internal Server Error: Database connection unavailable."}
             
        cursor = conn.cursor()
        cursor.execute("""
            SELECT face_encoding <-> %s::vector AS distance 
            FROM employees 
            WHERE employee_id = %s
        """, (str(incoming_vector), employee_id))
        
        result = cursor.fetchone()
        cursor.close()
        conn.close()

        if not result or result[0] is None:
            return {"success": False, "msg": f"Verification failed: Biometric profile not found for ID '{employee_id}'."}
            
        distance = result[0]
        
    except Exception as e:
        print(f"[ERROR] Vector proximity calculation failed: {e}")
        return {"success": False, "msg": "Internal Server Error: Database execution failed."}

    # Authentication Logic & Background Archival
    if distance <= MATCH_THRESHOLD:
        print(f"[SUCCESS] Authentication Passed. Euclidean Distance: {distance:.3f}")
        background_tasks.add_task(background_s3_upload, employee_id, contents, True)
        print(f"{'-'*50}")
        return {"success": True, "msg": "Authentication successful."}
    else:
        print(f"[WARNING] Authentication Failed. Euclidean Distance: {distance:.3f}")
        background_tasks.add_task(background_s3_upload, employee_id, contents, False)
        print(f"{'-'*50}")
        return {"success": False, "msg": "Authentication failed. Identity mismatch."}