import os
import boto3
from fastapi import APIRouter, Form, Request
from database import get_db_connection
from dotenv import load_dotenv

load_dotenv()
BUCKET_NAME = os.getenv("S3_BUCKET_NAME")

# Initialize AWS S3 Client
s3_client = boto3.client(
    's3',
    aws_access_key_id=os.getenv("AWS_ACCESS_KEY_ID"),
    aws_secret_access_key=os.getenv("AWS_SECRET_ACCESS_KEY"),
    region_name=os.getenv("AWS_REGION")
)

router = APIRouter()

def delete_s3_prefix(prefix: str):
    """Helper function to delete all objects under a specific S3 path."""
    try:
        paginator = s3_client.get_paginator('list_objects_v2')
        pages = paginator.paginate(Bucket=BUCKET_NAME, Prefix=prefix)
        
        delete_list = dict(Objects=[])
        for item in pages.search('Contents'):
            if item:
                delete_list['Objects'].append({'Key': item['Key']})
                
                # S3 delete_objects API accepts a maximum of 1000 keys at once
                if len(delete_list['Objects']) >= 1000:
                    s3_client.delete_objects(Bucket=BUCKET_NAME, Delete=delete_list)
                    delete_list = dict(Objects=[])
        
        # Delete remaining objects
        if len(delete_list['Objects']) > 0:
            s3_client.delete_objects(Bucket=BUCKET_NAME, Delete=delete_list)
            
    except Exception as e:
        print(f"[ERROR] S3 Cleanup failed for path '{prefix}': {e}")

@router.post("/delete_employee")
async def delete_employee(
    request: Request,
    employee_id: str = Form(default=None)
):
    print(f"\n{'-'*50}")
    print(f"[INFO] Incoming API Request: /delete_employee for ID: {employee_id}")

    if not employee_id:
        return {"success": False, "msg": "Invalid request. Missing Employee ID."}

    # Step 1: Delete from Cloud Database
    try:
        conn = get_db_connection()
        if conn is None:
             return {"success": False, "msg": "Internal Server Error: Database connection unavailable."}
             
        cursor = conn.cursor()
        
        # Check if employee exists
        cursor.execute("SELECT 1 FROM employees WHERE employee_id = %s", (employee_id,))
        if not cursor.fetchone():
            cursor.close()
            conn.close()
            return {"success": False, "msg": f"Deletion failed: Employee ID '{employee_id}' not found."}

        # Delete the record
        cursor.execute("DELETE FROM employees WHERE employee_id = %s", (employee_id,))
        conn.commit()
        cursor.close()
        conn.close()
        print(f"[SUCCESS] Biometric profile for ID '{employee_id}' securely removed from Database.")
        
    except Exception as e:
        print(f"[ERROR] Database deletion failed: {e}")
        return {"success": False, "msg": "Internal Server Error: Database execution failed."}

    # Step 2: Delete from S3 Bucket (Register & Verify Folders)
    print(f"[INFO] Initiating S3 storage cleanup for ID: {employee_id}...")
    
    # Removes register/ID/*
    delete_s3_prefix(f"register/{employee_id}/")
    
    # Removes verify/ID/*
    delete_s3_prefix(f"verify/{employee_id}/")
    
    print(f"[SUCCESS] All associated cloud storage assets for ID '{employee_id}' permanently destroyed.")
    print(f"{'-'*50}\n")
    
    return {"success": True, "msg": f"Employee {employee_id} and all associated cloud assets have been completely removed."}