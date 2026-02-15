"""
Inaya Backend Server - Railway Deployment
Main FastAPI application with class management
"""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from dotenv import load_dotenv
import os

# Load environment variables
load_dotenv()

# Create FastAPI app
app = FastAPI(
    title="Inaya Backend API",
    description="School Management System Backend - Developed by Vertex",
    version="1.2.0",
    docs_url="/docs",
    redoc_url="/redoc"
)

# Configure CORS - Allow all origins for mobile app
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Allow all origins for mobile app
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ========== CLASS MANAGEMENT ROUTES ==========

from pydantic import BaseModel
from typing import Optional
import ftplib
import json
from fastapi import HTTPException

# FTP Configuration from environment variables
FTP_HOST = os.getenv("FTP_HOST", "ftp.ftpupload.net")
FTP_USER = os.getenv("FTP_USER", "")
FTP_PASS = os.getenv("FTP_PASS", "")
BASE_PATH = os.getenv("BASE_PATH", "/htdocs/classes")

# Request Models
class CreateClassRequest(BaseModel):
    class_name: str
    section: Optional[str] = None

class DeleteClassRequest(BaseModel):
    class_name: str

# Helper Functions
def get_ftp_connection():
    """Create and return FTP connection"""
    try:
        ftp = ftplib.FTP(FTP_HOST)
        ftp.login(FTP_USER, FTP_PASS)
        return ftp
    except ftplib.all_errors as e:
        raise HTTPException(status_code=500, detail=f"FTP connection failed: {str(e)}")

def normalize_class_name(class_name: str) -> str:
    """Normalize class name to lowercase and remove .json extension"""
    name = class_name.strip().lower()
    if name.endswith('.json'):
        name = name[:-5]
    return name

def create_empty_class_file(section: Optional[str] = None) -> dict:
    """Create empty class JSON structure"""
    return {"students": {}}

# ========== API ENDPOINTS ==========

@app.get("/")
async def root():
    """Root endpoint - API status"""
    return {
        "message": "Inaya Backend API",
        "version": "1.2.0",
        "status": "running",
        "developer": "Vertex"
    }

@app.get("/health")
async def health_check():
    """Health check endpoint"""
    return {
        "status": "healthy",
        "ftp_configured": bool(FTP_USER and FTP_PASS)
    }

@app.get("/classes")
async def get_all_classes():
    """Get list of all class files from FTP server"""
    ftp = None
    try:
        ftp = get_ftp_connection()
        ftp.cwd(BASE_PATH)
        
        # List all files
        files = ftp.nlst()
        
        # Filter JSON files and remove extension
        classes = []
        for file in files:
            if file.endswith('.json'):
                class_name = file[:-5].lower()
                classes.append(class_name)
        
        # Sort alphabetically
        classes.sort()
        
        return {
            "status": "success",
            "classes": classes,
            "total": len(classes)
        }
        
    except ftplib.error_perm as e:
        raise HTTPException(status_code=404, detail="Classes directory not found")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to list classes: {str(e)}")
    finally:
        if ftp:
            try:
                ftp.quit()
            except:
                pass

@app.post("/classes/create")
async def create_class(request: CreateClassRequest):
    """Create new class JSON file on FTP server"""
    ftp = None
    try:
        # Normalize class name to lowercase
        normalized_name = normalize_class_name(request.class_name)
        
        if not normalized_name:
            raise HTTPException(status_code=400, detail="Class name cannot be empty")
        
        # Connect to FTP
        ftp = get_ftp_connection()
        
        # Check if file already exists
        try:
            ftp.cwd(BASE_PATH)
            existing_files = ftp.nlst()
            if f"{normalized_name}.json" in existing_files:
                raise HTTPException(
                    status_code=409,
                    detail=f"Class '{normalized_name}' already exists"
                )
        except ftplib.error_perm:
            # Directory doesn't exist, create it
            try:
                ftp.mkd(BASE_PATH)
                ftp.cwd(BASE_PATH)
            except:
                pass
        
        # Create empty class file content
        class_data = create_empty_class_file(request.section)
        json_content = json.dumps(class_data, indent=2)
        
        # Upload file to FTP
        from io import BytesIO
        file_buffer = BytesIO(json_content.encode('utf-8'))
        ftp.storbinary(f"STOR {normalized_name}.json", file_buffer)
        
        return {
            "status": "success",
            "message": f"Class '{normalized_name}' created successfully",
            "class_name": normalized_name,
            "file_name": f"{normalized_name}.json",
            "file_path": f"{BASE_PATH}/{normalized_name}.json"
        }
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to create class: {str(e)}")
    finally:
        if ftp:
            try:
                ftp.quit()
            except:
                pass

@app.delete("/classes/delete")
async def delete_class(request: DeleteClassRequest):
    """Delete class JSON file from FTP server"""
    ftp = None
    try:
        # Normalize class name
        normalized_name = normalize_class_name(request.class_name)
        
        # Connect to FTP
        ftp = get_ftp_connection()
        ftp.cwd(BASE_PATH)
        
        # Check if file exists
        existing_files = ftp.nlst()
        if f"{normalized_name}.json" not in existing_files:
            raise HTTPException(
                status_code=404,
                detail=f"Class '{normalized_name}' not found"
            )
        
        # Delete the file
        ftp.delete(f"{normalized_name}.json")
        
        return {
            "status": "success",
            "message": f"Class '{normalized_name}' deleted successfully",
            "class_name": normalized_name
        }
        
    except HTTPException:
        raise
    except ftplib.error_perm:
        raise HTTPException(status_code=404, detail="Class not found or permission denied")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to delete class: {str(e)}")
    finally:
        if ftp:
            try:
                ftp.quit()
            except:
                pass

@app.get("/classes/{class_name}/exists")
async def check_class_exists(class_name: str):
    """Check if a class file exists"""
    ftp = None
    try:
        normalized_name = normalize_class_name(class_name)
        
        ftp = get_ftp_connection()
        ftp.cwd(BASE_PATH)
        
        existing_files = ftp.nlst()
        exists = f"{normalized_name}.json" in existing_files
        
        return {
            "status": "success",
            "class_name": normalized_name,
            "exists": exists
        }
        
    except Exception as e:
        return {
            "status": "error",
            "exists": False,
            "message": str(e)
        }
    finally:
        if ftp:
            try:
                ftp.quit()
            except:
                pass

# ========== STUDENT MANAGEMENT ROUTES ==========

@app.get("/students/{class_name}")
async def get_students(class_name: str):
    """Get students for a specific class from FTP"""
    ftp = None
    try:
        normalized_name = normalize_class_name(class_name)
        
        # Connect to FTP
        ftp = get_ftp_connection()
        ftp.cwd(BASE_PATH)
        
        # Download the JSON file
        from io import BytesIO
        file_buffer = BytesIO()
        ftp.retrbinary(f"RETR {normalized_name}.json", file_buffer.write)
        
        # Parse JSON
        file_buffer.seek(0)
        data = json.loads(file_buffer.read().decode('utf-8'))
        
        return data
        
    except ftplib.error_perm:
        raise HTTPException(status_code=404, detail=f"Class '{class_name}' not found")
    except json.JSONDecodeError:
        raise HTTPException(status_code=500, detail="Invalid JSON in class file")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to get students: {str(e)}")
    finally:
        if ftp:
            try:
                ftp.quit()
            except:
                pass

# ========== ERROR HANDLERS ==========

@app.exception_handler(404)
async def not_found_handler(request, exc):
    return {
        "status": "error",
        "message": "Resource not found",
        "detail": str(exc)
    }

@app.exception_handler(500)
async def server_error_handler(request, exc):
    return {
        "status": "error",
        "message": "Internal server error",
        "detail": str(exc)
    }

# ========== STARTUP/SHUTDOWN EVENTS ==========

@app.on_event("startup")
async def startup_event():
    """Run on application startup"""
    print("=" * 50)
    print("Inaya Backend API - Starting")
    print(f"FTP Host: {FTP_HOST}")
    print(f"Base Path: {BASE_PATH}")
    print("=" * 50)

@app.on_event("shutdown")
async def shutdown_event():
    """Run on application shutdown"""
    print("Inaya Backend API - Shutting down")

# This is required for Railway deployment
if __name__ == "__main__":
    import uvicorn
    port = int(os.getenv("PORT", 8000))
    uvicorn.run(app, host="0.0.0.0", port=port)
