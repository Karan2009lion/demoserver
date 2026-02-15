"""
Inaya Backend Server - Railway Deployment
Main FastAPI application with class management
"""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
import os

# NO dotenv needed - Railway provides env vars directly

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
    """Create and return FTP connection with better error handling"""
    try:
        print(f"[DEBUG] Attempting FTP connection to {FTP_HOST}")
        ftp = ftplib.FTP(FTP_HOST, timeout=30)
        print(f"[DEBUG] FTP object created, attempting login...")
        ftp.login(FTP_USER, FTP_PASS)
        print(f"[DEBUG] FTP login successful")
        return ftp
    except ftplib.error_perm as e:
        error_msg = f"FTP Login Failed - Invalid credentials: {str(e)}"
        print(f"[ERROR] {error_msg}")
        raise HTTPException(
            status_code=500,
            detail=f"{error_msg}. Check FTP_USER and FTP_PASS environment variables."
        )
    except Exception as e:
        error_msg = f"FTP Connection Failed: {str(e)}"
        print(f"[ERROR] {error_msg}")
        raise HTTPException(
            status_code=500,
            detail=f"{error_msg}. Check FTP_HOST environment variable and network connectivity."
        )

def normalize_class_name(class_name: str) -> str:
    """Normalize class name to lowercase and remove .json extension"""
    name = class_name.strip().lower()
    if name.endswith('.json'):
        name = name[:-5]
    return name

def create_empty_class_file(section: Optional[str] = None) -> dict:
    """Create empty class JSON structure"""
    return {}

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
    """Health check endpoint with configuration status"""
    return {
        "status": "healthy",
        "ftp_configured": bool(FTP_USER and FTP_PASS),
        "ftp_host": FTP_HOST if FTP_HOST else "NOT_SET",
        "ftp_user": FTP_USER if FTP_USER else "NOT_SET",
        "ftp_pass_set": "YES" if FTP_PASS else "NO",
        "base_path": BASE_PATH if BASE_PATH else "NOT_SET"
    }

@app.get("/debug/config")
async def debug_config():
    """Debug endpoint to check environment variables (DO NOT USE IN PRODUCTION)"""
    return {
        "ftp_host": FTP_HOST or "NOT_SET",
        "ftp_user": FTP_USER or "NOT_SET",
        "ftp_pass_length": len(FTP_PASS) if FTP_PASS else 0,
        "ftp_pass_set": bool(FTP_PASS),
        "base_path": BASE_PATH or "NOT_SET",
        "all_env_vars": {
            key: value for key, value in os.environ.items() 
            if key.startswith('FTP_') or key in ['BASE_PATH', 'PORT']
        }
    }

@app.get("/classes")
async def get_all_classes():
    """Get list of all class files from FTP server"""
    ftp = None
    try:
        # Log FTP configuration (without password)
        print(f"[DEBUG] Connecting to FTP: {FTP_HOST}")
        print(f"[DEBUG] FTP User: {FTP_USER}")
        print(f"[DEBUG] Base Path: {BASE_PATH}")
        
        # Check if FTP credentials are configured
        if not FTP_USER or not FTP_PASS:
            raise HTTPException(
                status_code=500,
                detail="FTP credentials not configured. Please set FTP_USER and FTP_PASS environment variables."
            )
        
        ftp = get_ftp_connection()
        print(f"[DEBUG] FTP connected successfully")
        
        # Try to change to BASE_PATH directory
        try:
            ftp.cwd(BASE_PATH)
            print(f"[DEBUG] Changed to directory: {BASE_PATH}")
        except ftplib.error_perm as e:
            print(f"[DEBUG] Directory {BASE_PATH} not found, creating it...")
            # Try to create the directory
            try:
                # Split path and create each part
                parts = BASE_PATH.strip('/').split('/')
                current_path = ''
                for part in parts:
                    current_path += f'/{part}'
                    try:
                        ftp.mkd(current_path)
                        print(f"[DEBUG] Created directory: {current_path}")
                    except:
                        pass  # Directory might already exist
                ftp.cwd(BASE_PATH)
            except Exception as create_error:
                raise HTTPException(
                    status_code=500,
                    detail=f"Cannot access or create directory {BASE_PATH}. Error: {str(create_error)}"
                )
        
        # List all files in the directory
        files = []
        try:
            files = ftp.nlst()
            print(f"[DEBUG] Found {len(files)} files in directory")
        except ftplib.error_perm:
            # Directory is empty
            print(f"[DEBUG] Directory is empty")
            files = []
        
        # Filter JSON files and remove extension
        classes = []
        for file in files:
            if file.endswith('.json'):
                class_name = file[:-5].lower()
                classes.append(class_name)
                print(f"[DEBUG] Found class: {class_name}")
        
        # Sort alphabetically
        classes.sort()
        
        print(f"[DEBUG] Returning {len(classes)} classes")
        
        return {
            "status": "success",
            "classes": classes,
            "total": len(classes),
            "ftp_host": FTP_HOST,
            "base_path": BASE_PATH
        }
        
    except HTTPException:
        raise
    except ftplib.error_perm as e:
        error_msg = f"FTP Permission Error: {str(e)}"
        print(f"[ERROR] {error_msg}")
        raise HTTPException(
            status_code=500,
            detail=f"{error_msg}. Check FTP credentials and permissions."
        )
    except ftplib.all_errors as e:
        error_msg = f"FTP Error: {str(e)}"
        print(f"[ERROR] {error_msg}")
        raise HTTPException(
            status_code=500,
            detail=f"{error_msg}. Check FTP_HOST, FTP_USER, FTP_PASS in environment variables."
        )
    except Exception as e:
        error_msg = f"Unexpected error: {str(e)}"
        print(f"[ERROR] {error_msg}")
        import traceback
        traceback.print_exc()
        raise HTTPException(
            status_code=500,
            detail=error_msg
        )
    finally:
        if ftp:
            try:
                ftp.quit()
                print(f"[DEBUG] FTP connection closed")
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

@app.get("/students/{class_name}")
async def get_students(class_name: str):
    try:
        file_path = f"{BASE_PATH}/{class_name}.json"
        students_db = await ftp_read(file_path)

        if not students_db:
            return {
                "status": "error",
                "message": f"No students found for class {class_name}",
                "students": {}
            }

        # ✅ SUPPORTED BY BOTH APPS
        return {
            "status": "success",          # App-B requirement
            "class": class_name,
            "total_students": len(students_db),
            "students": students_db       # App-A & App-B requirement
        }

    except Exception as e:
        print("FETCH STUDENTS ERROR:", str(e))
        return {
            "status": "error",
            "message": str(e),
            "students": {}
        }



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
