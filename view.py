import os
import boto3
from fastapi import APIRouter
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

def get_presigned_url(key: str):
    """Generates a temporary secure URL (expires in 1 hour) for an S3 object."""
    try:
        return s3_client.generate_presigned_url(
            'get_object',
            Params={'Bucket': BUCKET_NAME, 'Key': key},
            ExpiresIn=3600 
        )
    except Exception as e:
        print(f"[ERROR] Presigned URL generation failed: {e}")
        return None

# ==========================================
# ENDPOINT 1: Get 3 Photos for a Specific ID
# ==========================================
@router.get("/get_employee_photos/{employee_id}")
async def get_employee_photos(employee_id: str):
    print(f"\n{'-'*50}")
    print(f"[INFO] Fetching registration photos for ID: {employee_id}")

    try:
        # Search S3 folder for this specific employee
        response = s3_client.list_objects_v2(Bucket=BUCKET_NAME, Prefix=f"register/{employee_id}/")
        
        if 'Contents' not in response:
            return {"success": False, "msg": f"No photos found for Employee ID: {employee_id}"}
            
        photo_urls = []
        for obj in response['Contents']:
            # Generate a secure link for each photo found
            url = get_presigned_url(obj['Key'])
            if url:
                photo_urls.append(url)
                
        print(f"[SUCCESS] Retrieved {len(photo_urls)} photos.")
        print(f"{'-'*50}\n")
        
        return {
            "success": True, 
            "employee_id": employee_id, 
            "photos": photo_urls
        }
        
    except Exception as e:
        print(f"[ERROR] S3 Fetch failed: {e}")
        return {"success": False, "msg": "Internal Server Error while fetching photos."}


# ==========================================
# ENDPOINT 2: Get All Employees & All 3 Photos
# ==========================================
@router.get("/get_all_employees")
async def get_all_employees():
    print(f"\n{'-'*50}")
    print("[INFO] Fetching all registered employees and their photos from database...")

    try:
        # Connect to Database[cite: 1]
        conn = get_db_connection()
        if conn is None:
             return {"success": False, "msg": "Database connection unavailable."}
             
        cursor = conn.cursor()
        cursor.execute("SELECT employee_id, name, status, training_status FROM employees")
        rows = cursor.fetchall()
        cursor.close()
        conn.close()

        employee_list = []
        
        # Loop through employees to attach all their registration photos
        for row in rows:
            emp_id = row[0]
            
            # Fetch all objects inside the register/{emp_id}/ folder without MaxKeys limit
            response = s3_client.list_objects_v2(Bucket=BUCKET_NAME, Prefix=f"register/{emp_id}/")
            
            photo_urls = []
            if 'Contents' in response:
                for obj in response['Contents']:
                    url = get_presigned_url(obj['Key'])
                    if url:
                        photo_urls.append(url)

            employee_list.append({
                "employee_id": emp_id,
                "name": row[1],
                "status": row[2],
                "training_status": row[3],
                "photos": photo_urls  # Ab yahan teeno photos ki array aayegi
            })

        print(f"[SUCCESS] Retrieved {len(employee_list)} employees with their photos.")
        print(f"{'-'*50}\n")
        
        return {
            "success": True, 
            "total_count": len(employee_list),
            "employees": employee_list
        }

    except Exception as e:
        print(f"[ERROR] Database or S3 execution failed: {e}")
        return {"success": False, "msg": "Internal Server Error."}