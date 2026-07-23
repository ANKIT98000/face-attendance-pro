from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from register import router as register_router
from verify import router as verify_router
from delete import router as delete_router  
from view import router as view_router 

# Initialize FastAPI App
app = FastAPI(
    title="Enterprise Face Recognition API", 
    description="Stateless Cloud Native API with Vector DB & S3 Storage",
    version="3.0"
)

# Configure CORS Middleware for cross-origin requests
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include application routers
app.include_router(register_router)
app.include_router(verify_router)
app.include_router(delete_router)    
app.include_router(view_router)

@app.get("/")
def check():
    return {
        "success": True, 
        "msg": "Face Recognition API is online ."
    }