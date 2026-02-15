from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import Optional
import ftplib
import json
import os

# ========== ROUTER SETUP ==========
router = APIRouter(prefix="/classes", tags=["Class Management"])

# ========== FTP CONFIGURATION ==========
# These should be loaded from environment variables or config
FTP_HOST = os.getenv("FTP_HOST", "ftp.ftpupload.net")
FTP_USER = os.getenv("FTP_USER", "your_username")
FTP_PASS = os.getenv("FTP_PASS", "your_password")
BASE_PATH = os.getenv("BASE_PATH", "/htdocs/classes")  # Path where class files are stored

# ========== REQUEST MODELS ==========
class CreateClassRequest(BaseModel):
    class_name: str
    section: Optional[str] = None

class DeleteClassRequest(BaseModel):
    class_name: str

# ========== HELPER FUNCTIONS ==========

def get_ftp_connection():
    """
    Create and return FTP connection
    """
    try:
        ftp = ftplib.FTP(FTP_HOST)
        ftp.login(FTP_USER, FTP_PASS)
        return ftp
    except ftplib.all_errors as e:
        raise HTTPException(status_code=500, detail=f"FTP connection failed: {str(e)}")

def normalize_class_name(class_name: str) -> str:
    """
    Normalize class name to lowercase and remove .json extension if present
    """
    name = class_name.strip().lower()
    if name.endswith('.json'):
        name = name[:-5]
    return name

def get_file_path(class_name: str) -> str:
    """
    Get full FTP path for class file
    """
    normalized_name = normalize_class_name(class_name)
    return f"{BASE_PATH}/{normalized_name}.json"

def create_empty_class_file(section: Optional[str] = None) -> dict:
    """
    Create empty class JSON structure
    """
    return {
        "students": {}
    }

# ========== API ENDPOINTS ==========

@router.get("")
async def get_all_classes():
    """
    Get list of all class files from FTP server
    Returns class names without .json extension, in lowercase
    """
    ftp = None
    try:
        ftp = get_ftp_connection()
        ftp.cwd(BASE_PATH)
        
        # List all files in the directory
        files = ftp.nlst()
        
        # Filter JSON files and remove extension
        classes = []
        for file in files:
            if file.endswith('.json'):
                # Remove .json extension and convert to lowercase
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

@router.post("/create")
async def create_class(request: CreateClassRequest):
    """
    Create new class JSON file on FTP server
    Class name will be converted to lowercase
    """
    ftp = None
    try:
        # Normalize class name to lowercase
        normalized_name = normalize_class_name(request.class_name)
        file_path = get_file_path(normalized_name)
        
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
            "file_path": file_path
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

@router.delete("/delete")
async def delete_class(request: DeleteClassRequest):
    """
    Delete class JSON file from FTP server
    """
    ftp = None
    try:
        # Normalize class name to lowercase
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
    except ftplib.error_perm as e:
        raise HTTPException(status_code=404, detail=f"Class not found or permission denied")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to delete class: {str(e)}")
    finally:
        if ftp:
            try:
                ftp.quit()
            except:
                pass

@router.get("/{class_name}/exists")
async def check_class_exists(class_name: str):
    """
    Check if a class file exists
    """
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
