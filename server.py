"""
Inaya Backend Server - Railway Deployment
Main FastAPI application with class management
"""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
import os
import aioftp
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


async def ftp_read(path):
    async with aioftp.Client.context(FTP_HOST, user=FTP_USER, password=FTP_PASS) as client:
        if await client.exists(path):
            async with client.download_stream(path) as stream:
                content = await stream.read()
                return json.loads(content.decode())
        return {}

async def ftp_write(path, data):
    async with aioftp.Client.context(FTP_HOST, user=FTP_USER, password=FTP_PASS) as client:
        binary_data = json.dumps(data, indent=2).encode()
        async with client.upload_stream(path) as stream:
            await stream.write(binary_data)

async def ftp_ensure_dir(dir_path: str):
    async with aioftp.Client.context(FTP_HOST, user=FTP_USER, password=FTP_PASS) as client:
        try:
            await client.make_directory(dir_path, parents=True)
        except aioftp.StatusCodeError:
            pass  # Directory already exists


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


# ========== FEE MANAGEMENT ROUTES ==========

class SetFeeRequest(BaseModel):
    class_name: str
    tuition_fees: int = 0
    lab_fees: int = 0
    miscellaneous_fees: int = 0

class DeleteFeeRequest(BaseModel):
    class_name: str

@app.get("/fees")
async def get_all_fees():
    """Get all class fees from single fees.json file"""
    ftp = None
    try:
        # Connect to FTP
        ftp = get_ftp_connection()
        ftp.cwd(BASE_PATH)
        
        # Download the fees.json file
        from io import BytesIO
        file_buffer = BytesIO()
        try:
            ftp.retrbinary("RETR fees.json", file_buffer.write)
        except ftplib.error_perm:
            # fees.json doesn't exist, return empty
            return {
                "status": "success",
                "class_fees": {},
                "total_classes": 0
            }
        
        # Parse JSON
        file_buffer.seek(0)
        fee_data = json.loads(file_buffer.read().decode('utf-8'))
        
        return {
            "status": "success",
            "class_fees": fee_data.get("class_fees", {}),
            "total_classes": len(fee_data.get("class_fees", {}))
        }
        
    except json.JSONDecodeError:
        raise HTTPException(status_code=500, detail="Invalid JSON in fees file")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to get fees: {str(e)}")
    finally:
        if ftp:
            try:
                ftp.quit()
            except:
                pass

@app.post("/fees/set")
async def set_fee_structure(request: SetFeeRequest):
    """Set or update fee structure for a class in single fees.json file"""
    ftp = None
    try:
        # Normalize class name
        normalized_name = normalize_class_name(request.class_name)
        
        # Calculate total fees
        total_fees = (
            request.tuition_fees +
            request.lab_fees +
            request.miscellaneous_fees
        )
        
        # Connect to FTP
        ftp = get_ftp_connection()
        
        try:
            ftp.cwd(BASE_PATH)
        except ftplib.error_perm:
            # Directory doesn't exist, create it
            try:
                ftp.mkd(BASE_PATH)
                ftp.cwd(BASE_PATH)
            except:
                pass
        
        # Download existing fees.json or create new
        from io import BytesIO
        all_fees = {"class_fees": {}}
        
        try:
            file_buffer = BytesIO()
            ftp.retrbinary("RETR fees.json", file_buffer.write)
            file_buffer.seek(0)
            all_fees = json.loads(file_buffer.read().decode('utf-8'))
        except ftplib.error_perm:
            # fees.json doesn't exist yet
            pass
        except json.JSONDecodeError:
            # Invalid JSON, start fresh
            pass
        
        # Update the specific class fees
        all_fees["class_fees"][normalized_name] = {
            "class_name": normalized_name,
            "tuition_fees": request.tuition_fees,
            "lab_fees": request.lab_fees,
            "miscellaneous_fees": request.miscellaneous_fees,
            "total_fees": total_fees
        }
        
        # Upload updated fees.json
        json_content = json.dumps(all_fees, indent=2)
        file_buffer = BytesIO(json_content.encode('utf-8'))
        ftp.storbinary("STOR fees.json", file_buffer)
        
        return {
            "status": "success",
            "message": f"Fee structure set for class '{normalized_name}'",
            "class_name": normalized_name,
            "total_fees": total_fees
        }
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to set fee structure: {str(e)}")
    finally:
        if ftp:
            try:
                ftp.quit()
            except:
                pass

@app.delete("/fees/delete")
async def delete_fee_structure(request: DeleteFeeRequest):
    """Delete fee structure for a class from fees.json"""
    ftp = None
    try:
        # Normalize class name
        normalized_name = normalize_class_name(request.class_name)
        
        # Connect to FTP
        ftp = get_ftp_connection()
        ftp.cwd(BASE_PATH)
        
        # Download existing fees.json
        from io import BytesIO
        file_buffer = BytesIO()
        try:
            ftp.retrbinary("RETR fees.json", file_buffer.write)
        except ftplib.error_perm:
            raise HTTPException(
                status_code=404,
                detail="Fees file not found"
            )
        
        file_buffer.seek(0)
        all_fees = json.loads(file_buffer.read().decode('utf-8'))
        
        # Check if class exists
        if normalized_name not in all_fees.get("class_fees", {}):
            raise HTTPException(
                status_code=404,
                detail=f"Fee structure not found for class '{normalized_name}'"
            )
        
        # Remove the class
        del all_fees["class_fees"][normalized_name]
        
        # Upload updated fees.json
        json_content = json.dumps(all_fees, indent=2)
        file_buffer = BytesIO(json_content.encode('utf-8'))
        ftp.storbinary("STOR fees.json", file_buffer)
        
        return {
            "status": "success",
            "message": f"Fee structure deleted for class '{normalized_name}'",
            "class_name": normalized_name
        }
        
    except HTTPException:
        raise
    except json.JSONDecodeError:
        raise HTTPException(status_code=500, detail="Invalid JSON in fees file")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to delete fee structure: {str(e)}")
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


# ========== COMPLETE STUDENT FEE MANAGEMENT SYSTEM (FINAL) ==========
# Features: FTP PDF storage, auto-cleanup, reprint functionality
# REPLACE your current fee management code with this

from datetime import datetime, timedelta
import os
import glob
import tempfile

# Import ReportLab
try:
    from reportlab.lib.pagesizes import A4
    from reportlab.lib import colors
    from reportlab.lib.units import inch
    from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
    from reportlab.lib.enums import TA_CENTER, TA_RIGHT
    REPORTLAB_AVAILABLE = True
except ImportError:
    REPORTLAB_AVAILABLE = False
    print("[WARNING] ReportLab not installed")

# ========== HELPER FUNCTIONS ==========

def normalize_student_data(class_data):
    """Handle both JSON formats"""
    if not isinstance(class_data, dict):
        return {"students": {}}
    
    if "students" in class_data and isinstance(class_data["students"], dict):
        return class_data
    
    students = {k: v for k, v in class_data.items() if isinstance(v, dict)}
    return {"students": students, "_direct_format": True}

def prepare_for_save(class_data):
    """Convert back to original format"""
    if class_data.get("_direct_format") == True:
        return class_data.get("students", {})
    return class_data

def get_class_total_fees(class_name):
    """Get total fees from fees.json"""
    ftp = None
    try:
        normalized_name = normalize_class_name(class_name)
        ftp = get_ftp_connection()
        ftp.cwd(BASE_PATH)
        
        from io import BytesIO
        file_buffer = BytesIO()
        try:
            ftp.retrbinary("RETR fees.json", file_buffer.write)
            file_buffer.seek(0)
            fees_data = json.loads(file_buffer.read().decode('utf-8'))
            return fees_data.get("class_fees", {}).get(normalized_name, {}).get("total_fees", 0)
        except:
            return 0
    finally:
        if ftp:
            try:
                ftp.quit()
            except:
                pass

def get_next_invoice_number():
    """Get next invoice number"""
    ftp = None
    try:
        ftp = get_ftp_connection()
        ftp.cwd(BASE_PATH)
        
        from io import BytesIO
        file_buffer = BytesIO()
        try:
            ftp.retrbinary("RETR invoice_records.json", file_buffer.write)
            file_buffer.seek(0)
            invoice_data = json.loads(file_buffer.read().decode('utf-8'))
            return invoice_data.get("next_invoice_number", 1)
        except:
            return 1
    finally:
        if ftp:
            try:
                ftp.quit()
            except:
                pass

def save_invoice_record(invoice):
    """Save invoice record"""
    ftp = None
    try:
        ftp = get_ftp_connection()
        ftp.cwd(BASE_PATH)
        
        from io import BytesIO
        invoice_data = {"invoices": [], "next_invoice_number": 1}
        
        try:
            file_buffer = BytesIO()
            ftp.retrbinary("RETR invoice_records.json", file_buffer.write)
            file_buffer.seek(0)
            invoice_data = json.loads(file_buffer.read().decode('utf-8'))
        except:
            pass
        
        invoice_data["invoices"].append(invoice)
        invoice_data["next_invoice_number"] = invoice_data.get("next_invoice_number", 1) + 1
        
        json_content = json.dumps(invoice_data, indent=2)
        file_buffer = BytesIO(json_content.encode('utf-8'))
        ftp.storbinary("STOR invoice_records.json", file_buffer)
        
        print(f"[DEBUG] Invoice saved: {invoice['invoice_number']}")
        return invoice_data["next_invoice_number"] - 1
    finally:
        if ftp:
            try:
                ftp.quit()
            except:
                pass

def generate_and_upload_pdf(invoice_number, student_data, amount_paid, note, created_by):
    """Generate PDF and upload to FTP"""
    
    if not REPORTLAB_AVAILABLE:
        raise Exception("PDF generation not available")
    
    ftp = None
    try:
        # Generate PDF in temp location
        with tempfile.NamedTemporaryFile(mode='wb', suffix='.pdf', delete=False) as tmp_file:
            temp_pdf_path = tmp_file.name
        
        print(f"[DEBUG] Creating PDF: {temp_pdf_path}")
        
        doc = SimpleDocTemplate(
            temp_pdf_path,
            pagesize=(A4[0], A4[1]/2),
            topMargin=0.5*inch,
            bottomMargin=0.5*inch,
            leftMargin=0.75*inch,
            rightMargin=0.75*inch
        )
        
        elements = []
        styles = getSampleStyleSheet()
        
        title_style = ParagraphStyle(
            'CustomTitle',
            parent=styles['Heading1'],
            fontSize=18,
            textColor=colors.HexColor('#0A1F44'),
            alignment=TA_CENTER,
            spaceAfter=12,
        )
        
        header_style = ParagraphStyle(
            'Header',
            parent=styles['Normal'],
            fontSize=10,
            alignment=TA_CENTER,
            spaceAfter=6,
        )
        
        # School name
        school_name = Paragraph("INAYA SCHOOL", title_style)
        elements.append(school_name)
        elements.append(Spacer(1, 0.1*inch))
        
        # Invoice header
        invoice_header = Paragraph(
            f"<b>INVOICE NO:</b> INV-{invoice_number:05d} | <b>DATE:</b> {datetime.now().strftime('%d-%b-%Y')}",
            header_style
        )
        elements.append(invoice_header)
        elements.append(Spacer(1, 0.2*inch))
        
        # Student details
        student_details = [
            ['Student Name:', str(student_data.get('name', 'N/A'))],
            ['Class:', str(student_data.get('class', 'N/A')).upper()],
            ['Father Name:', str(student_data.get('father', 'N/A'))],
            ['Phone:', str(student_data.get('phone', 'N/A'))],
        ]
        
        student_table = Table(student_details, colWidths=[1.5*inch, 3.5*inch])
        student_table.setStyle(TableStyle([
            ('FONTNAME', (0, 0), (0, -1), 'Helvetica-Bold'),
            ('FONTSIZE', (0, 0), (-1, -1), 10),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 6),
        ]))
        
        elements.append(student_table)
        elements.append(Spacer(1, 0.2*inch))
        
        # Fee items
        fee_data = [
            ['Description', 'Amount'],
            ['School Fees', f"₹{amount_paid}"],
        ]
        
        fee_table = Table(fee_data, colWidths=[3.5*inch, 1.5*inch])
        fee_table.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#0A1F44')),
            ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
            ('ALIGN', (1, 0), (1, -1), 'RIGHT'),
            ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
            ('FONTSIZE', (0, 0), (-1, -1), 10),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 8),
            ('GRID', (0, 0), (-1, -1), 1, colors.black),
        ]))
        
        elements.append(fee_table)
        elements.append(Spacer(1, 0.2*inch))
        
        # Totals
        totals_data = [
            ['Total Fees:', f"₹{student_data.get('totalfees', 0)}"],
            ['Amount Paid:', f"₹{amount_paid}"],
            ['Balance:', f"₹{student_data.get('feesremaining', 0)}"],
        ]
        
        totals_table = Table(totals_data, colWidths=[3.5*inch, 1.5*inch])
        totals_table.setStyle(TableStyle([
            ('ALIGN', (1, 0), (1, -1), 'RIGHT'),
            ('FONTNAME', (0, -1), (-1, -1), 'Helvetica-Bold'),
            ('FONTSIZE', (0, 0), (-1, -1), 10),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 6),
        ]))
        
        elements.append(totals_table)
        elements.append(Spacer(1, 0.3*inch))
        
        # Note
        if note and note.strip():
            note_para = Paragraph(f"<b>Note:</b> {note}", styles['Normal'])
            elements.append(note_para)
            elements.append(Spacer(1, 0.2*inch))
        
        # Signature
        signature = Paragraph("_____________________<br/>Admin Signature", styles['Normal'])
        elements.append(signature)
        
        # Build PDF
        doc.build(elements)
        print(f"[DEBUG] PDF created locally")
        
        # Upload to FTP
        ftp = get_ftp_connection()
        ftp.cwd(BASE_PATH)
        
        # Create PDF directory if doesn't exist
        try:
            ftp.cwd("pdf")
        except:
            print(f"[DEBUG] Creating pdf directory")
            ftp.mkd("pdf")
            ftp.cwd("pdf")
        
        # Upload PDF
        pdf_filename = f"INV-{invoice_number:05d}.pdf"
        with open(temp_pdf_path, 'rb') as pdf_file:
            ftp.storbinary(f"STOR {pdf_filename}", pdf_file)
        
        print(f"[DEBUG] ✅ PDF uploaded to FTP: pdf/{pdf_filename}")
        
        # Delete local temp file
        try:
            os.remove(temp_pdf_path)
        except:
            pass
        
        # Return FTP path
        return f"pdf/{pdf_filename}"
        
    except Exception as e:
        print(f"[ERROR] PDF generation/upload: {str(e)}")
        import traceback
        traceback.print_exc()
        raise
    finally:
        if ftp:
            try:
                ftp.quit()
            except:
                pass

def cleanup_old_pdfs():
    """
    Delete PDFs older than 1 day OR keep only last 5 PDFs
    Runs after every invoice generation
    """
    ftp = None
    try:
        ftp = get_ftp_connection()
        ftp.cwd(BASE_PATH)
        
        try:
            ftp.cwd("pdf")
        except:
            print(f"[DEBUG] No pdf directory to cleanup")
            return
        
        # Get list of PDF files with timestamps
        files = []
        try:
            ftp.retrlines('MLSD', lambda x: files.append(x))
        except:
            # Fallback to NLST if MLSD not supported
            filenames = []
            ftp.retrlines('NLST', filenames.append)
            files = [f"name={f}" for f in filenames if f.endswith('.pdf')]
        
        pdf_files = []
        for file_info in files:
            parts = dict(item.split('=', 1) for item in file_info.split('; ') if '=' in item)
            if 'name' in parts and parts['name'].endswith('.pdf'):
                # Get modification time
                modify_time = parts.get('modify', '')
                pdf_files.append({
                    'name': parts['name'],
                    'modify': modify_time
                })
        
        print(f"[DEBUG] Found {len(pdf_files)} PDFs on FTP")
        
        # Strategy 1: Delete PDFs older than 1 day
        cutoff_date = (datetime.now() - timedelta(days=1)).strftime('%Y%m%d')
        deleted_old = 0
        
        for pdf in pdf_files[:]:
            if pdf['modify'] and pdf['modify'] < cutoff_date:
                try:
                    ftp.delete(pdf['name'])
                    pdf_files.remove(pdf)
                    deleted_old += 1
                    print(f"[CLEANUP] Deleted old PDF: {pdf['name']}")
                except:
                    pass
        
        # Strategy 2: Keep only last 5 PDFs
        if len(pdf_files) > 5:
            # Sort by modification time
            pdf_files.sort(key=lambda x: x['modify'] or '')
            
            # Delete oldest ones
            to_delete = len(pdf_files) - 5
            for i in range(to_delete):
                try:
                    ftp.delete(pdf_files[i]['name'])
                    print(f"[CLEANUP] Deleted excess PDF: {pdf_files[i]['name']}")
                except:
                    pass
        
        if deleted_old > 0:
            print(f"[CLEANUP] Deleted {deleted_old} old PDFs (>1 day)")
        
    except Exception as e:
        print(f"[ERROR] Cleanup failed: {str(e)}")
    finally:
        if ftp:
            try:
                ftp.quit()
            except:
                pass

def get_pdf_from_ftp(pdf_filename):
    """Download PDF from FTP and return as bytes"""
    ftp = None
    try:
        ftp = get_ftp_connection()
        ftp.cwd(BASE_PATH)
        ftp.cwd("pdf")
        
        from io import BytesIO
        file_buffer = BytesIO()
        ftp.retrbinary(f"RETR {pdf_filename}", file_buffer.write)
        file_buffer.seek(0)
        
        print(f"[DEBUG] Downloaded PDF: {pdf_filename}")
        return file_buffer.getvalue()
        
    except Exception as e:
        print(f"[ERROR] Failed to get PDF: {str(e)}")
        raise
    finally:
        if ftp:
            try:
                ftp.quit()
            except:
                pass

# ========== REQUEST MODELS ==========

class AddStudentRequest(BaseModel):
    class_name: str
    student_id: str
    rollno: str
    section: str
    father: str
    phone: str
    email: str
    address: str
    dob: str
    aadhar: str
    sex: str

class UpdateStudentRequest(BaseModel):
    class_name: str
    student_id: str
    updates: dict

class CollectFeeRequest(BaseModel):
    class_name: str
    student_id: str
    amount: int
    generate_invoice: bool = False
    created_by: str = "Admin"
    note: str = ""

class UpdateConcessionRequest(BaseModel):
    class_name: str
    student_id: str
    concession: int

# ========== ENDPOINTS ==========

@app.post("/students/add")
async def add_student(request: AddStudentRequest):
    """Add new student"""
    ftp = None
    try:
        normalized_class = normalize_class_name(request.class_name)
        total_fees = get_class_total_fees(normalized_class)
        
        ftp = get_ftp_connection()
        ftp.cwd(BASE_PATH)
        
        from io import BytesIO
        file_buffer = BytesIO()
        try:
            ftp.retrbinary(f"RETR {normalized_class}.json", file_buffer.write)
            file_buffer.seek(0)
            class_data = json.loads(file_buffer.read().decode('utf-8'))
        except:
            class_data = {}
        
        normalized_data = normalize_student_data(class_data)
        
        if request.student_id in normalized_data["students"]:
            return {"status": "error", "message": f"Student already exists"}
        
        normalized_data["students"][request.student_id] = {
            "father": request.father,
            "aadhar": request.aadhar,
            "address": request.address,
            "phone": request.phone,
            "email": request.email,
            "dob": request.dob,
            "sex": request.sex,
            "totalfees": total_fees,
            "feespaid": 0,
            "feesremaining": total_fees,
            "concession": 0,
            "sats": "",
            "class": normalized_class,
            "section": request.section,
            "rollno": request.rollno,
            "test": {},
            "performance": {}
        }
        
        save_data = prepare_for_save(normalized_data)
        json_content = json.dumps(save_data, indent=2)
        file_buffer = BytesIO(json_content.encode('utf-8'))
        ftp.storbinary(f"STOR {normalized_class}.json", file_buffer)
        
        return {"status": "success", "message": "Student added successfully"}
        
    except Exception as e:
        return {"status": "error", "message": str(e)}
    finally:
        if ftp:
            try:
                ftp.quit()
            except:
                pass

@app.post("/students/update")
async def update_student(request: UpdateStudentRequest):
    """Update student"""
    ftp = None
    try:
        normalized_class = normalize_class_name(request.class_name)
        
        ftp = get_ftp_connection()
        ftp.cwd(BASE_PATH)
        
        from io import BytesIO
        file_buffer = BytesIO()
        ftp.retrbinary(f"RETR {normalized_class}.json", file_buffer.write)
        file_buffer.seek(0)
        class_data = json.loads(file_buffer.read().decode('utf-8'))
        
        normalized_data = normalize_student_data(class_data)
        
        if request.student_id not in normalized_data["students"]:
            return {"status": "error", "message": "Student not found"}
        
        normalized_data["students"][request.student_id].update(request.updates)
        
        student = normalized_data["students"][request.student_id]
        if any(k in request.updates for k in ["totalfees", "feespaid", "concession"]):
            total = int(student.get("totalfees", 0))
            paid = int(student.get("feespaid", 0))
            conc = int(student.get("concession", 0))
            student["feesremaining"] = total - conc - paid
        
        save_data = prepare_for_save(normalized_data)
        json_content = json.dumps(save_data, indent=2)
        file_buffer = BytesIO(json_content.encode('utf-8'))
        ftp.storbinary(f"STOR {normalized_class}.json", file_buffer)
        
        return {"status": "success", "message": "Student updated successfully"}
        
    except Exception as e:
        return {"status": "error", "message": str(e)}
    finally:
        if ftp:
            try:
                ftp.quit()
            except:
                pass

@app.post("/students/collect-fee")
async def collect_student_fee(request: CollectFeeRequest):
    """Collect fee - Save OR Generate invoice + PDF"""
    ftp = None
    try:
        print(f"[DEBUG] Collect fee: {request.student_id}, Amount: {request.amount}")
        
        normalized_class = normalize_class_name(request.class_name)
        ftp = get_ftp_connection()
        ftp.cwd(BASE_PATH)
        
        from io import BytesIO
        file_buffer = BytesIO()
        ftp.retrbinary(f"RETR {normalized_class}.json", file_buffer.write)
        file_buffer.seek(0)
        class_data = json.loads(file_buffer.read().decode('utf-8'))
        
        normalized_data = normalize_student_data(class_data)
        
        if request.student_id not in normalized_data["students"]:
            return {"status": "error", "message": "Student not found"}
        
        student = normalized_data["students"][request.student_id]
        
        current_paid = int(student.get("feespaid", 0))
        student["feespaid"] = current_paid + request.amount
        
        total = int(student.get("totalfees", 0))
        conc = int(student.get("concession", 0))
        student["feesremaining"] = total - conc - student["feespaid"]
        
        save_data = prepare_for_save(normalized_data)
        json_content = json.dumps(save_data, indent=2)
        file_buffer = BytesIO(json_content.encode('utf-8'))
        ftp.storbinary(f"STOR {normalized_class}.json", file_buffer)
        
        print(f"[DEBUG] ✅ Fee saved")
        
        if not request.generate_invoice:
            return {
                "status": "success",
                "message": "Fee updated successfully",
                "fees_paid": student["feespaid"],
                "fees_remaining": student["feesremaining"]
            }
        
        # Generate invoice
        try:
            invoice_number = get_next_invoice_number()
            
            student_data = {
                "name": request.student_id,
                "class": normalized_class,
                "father": student.get("father", "N/A"),
                "phone": student.get("phone", "N/A"),
                "totalfees": total,
                "feesremaining": student["feesremaining"]
            }
            
            # Generate and upload PDF to FTP
            pdf_path = generate_and_upload_pdf(
                invoice_number,
                student_data,
                request.amount,
                request.note,
                request.created_by
            )
            
            invoice = {
                "invoice_number": f"INV-{invoice_number:05d}",
                "student_name": request.student_id,
                "class": normalized_class,
                "amount_paid": request.amount,
                "date": datetime.now().strftime("%Y-%m-%d"),
                "created_by": request.created_by,
                "note": request.note,
                "pdf_filename": pdf_path.split('/')[-1],  # Just filename
                "items": [{"description": "School Fees", "amount": request.amount}]
            }
            
            save_invoice_record(invoice)
            cleanup_old_pdfs()
            
            print(f"[DEBUG] ✅ Invoice generated: INV-{invoice_number:05d}")
            
            return {
                "status": "success",
                "message": "Invoice generated successfully",
                "invoice_number": f"INV-{invoice_number:05d}",
                "pdf_filename": invoice['pdf_filename'],
                "fees_paid": student["feespaid"],
                "fees_remaining": student["feesremaining"]
            }
            
        except Exception as pdf_error:
            print(f"[ERROR] Invoice generation: {str(pdf_error)}")
            return {
                "status": "partial_success",
                "message": f"Fee saved but invoice failed: {str(pdf_error)}",
                "fees_paid": student["feespaid"],
                "fees_remaining": student["feesremaining"]
            }
        
    except Exception as e:
        print(f"[ERROR] {str(e)}")
        return {"status": "error", "message": str(e)}
    finally:
        if ftp:
            try:
                ftp.quit()
            except:
                pass

@app.post("/students/update-concession")
async def update_student_concession(request: UpdateConcessionRequest):
    """Update concession"""
    ftp = None
    try:
        normalized_class = normalize_class_name(request.class_name)
        ftp = get_ftp_connection()
        ftp.cwd(BASE_PATH)
        
        from io import BytesIO
        file_buffer = BytesIO()
        ftp.retrbinary(f"RETR {normalized_class}.json", file_buffer.write)
        file_buffer.seek(0)
        class_data = json.loads(file_buffer.read().decode('utf-8'))
        
        normalized_data = normalize_student_data(class_data)
        
        if request.student_id not in normalized_data["students"]:
            return {"status": "error", "message": "Student not found"}
        
        student = normalized_data["students"][request.student_id]
        student["concession"] = request.concession
        
        total = int(student.get("totalfees", 0))
        paid = int(student.get("feespaid", 0))
        student["feesremaining"] = total - request.concession - paid
        
        save_data = prepare_for_save(normalized_data)
        json_content = json.dumps(save_data, indent=2)
        file_buffer = BytesIO(json_content.encode('utf-8'))
        ftp.storbinary(f"STOR {normalized_class}.json", file_buffer)
        
        return {
            "status": "success",
            "message": "Concession updated successfully",
            "concession": student["concession"],
            "fees_remaining": student["feesremaining"]
        }
        
    except Exception as e:
        return {"status": "error", "message": str(e)}
    finally:
        if ftp:
            try:
                ftp.quit()
            except:
                pass

@app.get("/invoices")
async def get_invoice_records():
    """Get all invoices"""
    ftp = None
    try:
        ftp = get_ftp_connection()
        ftp.cwd(BASE_PATH)
        
        from io import BytesIO
        file_buffer = BytesIO()
        try:
            ftp.retrbinary("RETR invoice_records.json", file_buffer.write)
            file_buffer.seek(0)
            invoice_data = json.loads(file_buffer.read().decode('utf-8'))
            
            return {
                "status": "success",
                "invoices": invoice_data.get("invoices", []),
                "total": len(invoice_data.get("invoices", []))
            }
        except:
            return {"status": "success", "invoices": [], "total": 0}
    except Exception as e:
        return {"status": "error", "message": str(e), "invoices": [], "total": 0}
    finally:
        if ftp:
            try:
                ftp.quit()
            except:
                pass

@app.get("/invoices/download/{pdf_filename}")
async def download_invoice_pdf(pdf_filename: str):
    """Download/reprint PDF from FTP"""
    try:
        print(f"[DEBUG] Downloading PDF: {pdf_filename}")
        
        # Get PDF from FTP
        pdf_bytes = get_pdf_from_ftp(pdf_filename)
        
        # Return as downloadable file
        from fastapi.responses import Response
        
        return Response(
            content=pdf_bytes,
            media_type="application/pdf",
            headers={
                "Content-Disposition": f"attachment; filename={pdf_filename}",
                "Content-Type": "application/pdf"
            }
        )
        
    except Exception as e:
        print(f"[ERROR] PDF download: {str(e)}")
        return {
            "status": "error",
            "message": f"Failed to download PDF: {str(e)}"
        }

# ========== END OF COMPLETE SYSTEM ==========
