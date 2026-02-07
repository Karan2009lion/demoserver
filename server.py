import os
import json
import io
import pandas as pd
from datetime import datetime
from fastapi import FastAPI, HTTPException, UploadFile, File, Form
from fastapi.middleware.cors import CORSMiddleware
import aioftp
from google.cloud import firestore
from google.oauth2 import service_account
from pydantic import BaseModel
from typing import List, Optional


# ========= FIRESTORE SETUP =========
firestore_db = None

firebase_creds_json = os.getenv("GOOGLE_APPLICATION_CREDENTIALS_JSON")

if firebase_creds_json:
    try:
        creds_dict = json.loads(firebase_creds_json)
        credentials = service_account.Credentials.from_service_account_info(creds_dict)
        firestore_db = firestore.Client(credentials=credentials)
        print("✅ Firestore initialized successfully")
    except Exception as e:
        print("❌ Firestore init failed:", e)
else:
    print("⚠️ Firestore credentials not found in environment variables")


CLASS_COURSE_FILES = {
    "11": {
        "PCMC": [
            "chanakya.json",
            "gowthamma.json"
        ],
        "PCMB": [
            "11_pc_mb_section_a.json"
        ]
    },
    "12": {
        "PCMC": [
            "12_pc_mc_section_a.json",
            "12_pc_mc_section_b.json"
        ],
        "PCMB": [
            "12_pc_mb_section_a.json"
        ]
    }
}

# ========= PYDANTIC MODELS =========
class SectionTransferRequest(BaseModel):
    source_section: str
    target_section: str
    students: List[str]


class NoticeCreateRequest(BaseModel):
    author: str
    title: str
    content: str
    urgency: str  # "urgent", "medium", "low"


app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# Config
FTP_HOST = os.getenv("FTP_HOST")
FTP_USER = os.getenv("FTP_USER")
FTP_PASS = os.getenv("FTP_PASS")
BASE_PATH = os.getenv("BASE_PATH", "htdocs/Database_1")

# Notice system paths
NOTICES_BASE_PATH = "htdocs/notices"
TEACHERS_NOTICES_PATH = f"{NOTICES_BASE_PATH}/teachers.json"


# ========= FTP HELPERS =========
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


@app.post("/students/upload-marks")
async def upload_marks_by_class_course(
    file: UploadFile = File(...),
    test_name: str = Form(...),
    class_level: str = Form(...),
    course: str = Form(...),
    tot_marks: int = Form(...)
):
    if class_level not in CLASS_COURSE_FILES:
        raise HTTPException(400, "Invalid class level")

    if course not in CLASS_COURSE_FILES[class_level]:
        raise HTTPException(400, "Invalid course")
    if tot_marks <= 0:
        raise HTTPException(400, "Total marks must be positive")

    # 📊 Helper function to calculate grade from percentage
    def calculate_grade(percentage: float) -> str:
        if percentage >= 90:
            return 'A+'
        elif percentage >= 80:
            return 'A'
        elif percentage >= 70:
            return 'B+'
        elif percentage >= 60:
            return 'B'
        elif percentage >= 50:
            return 'C'
        elif percentage >= 40:
            return 'D'
        else:
            return 'F'

    try:
        contents = await file.read()

        # 🔁 Excel parsing — UNCHANGED
        try:
            df = pd.read_excel(io.BytesIO(contents), header=4)
        except:
            df = None

        if df is None or "Student Name" not in df.columns:
            raw_df = pd.read_excel(io.BytesIO(contents), header=None)
            header_row = None
            for i in range(len(raw_df)):
                row = raw_df.iloc[i].astype(str).str.lower().tolist()
                if "student name" in row:
                    header_row = i
                    break
            if header_row is None:
                raise HTTPException(400, "Student Name header not found")
            df = pd.read_excel(io.BytesIO(contents), header=header_row)

        df.columns = [str(c).strip() for c in df.columns]

        required = ["Student Name", "Physics", "Chemistry", "Maths"]
        optional = ["Bio/Cs"]
        subjects = required[1:] + [c for c in optional if c in df.columns]

        files_to_check = CLASS_COURSE_FILES[class_level][course]

        updated_students = 0
        not_found_students = []

        for _, row in df.iterrows():
            student_name = str(row["Student Name"]).strip()
            if not student_name or student_name.lower() in ("nan", "none"):
                continue

            student_updated = False

            for fname in files_to_check:
                path = f"{BASE_PATH}/{fname}"
                students_db = await ftp_read(path)

                if students_db is None:
                    continue  # file doesn't exist
                for key in students_db.keys():
                    print(f"Checking {student_name} in file: {fname}")

                    if key.strip().lower() == student_name.lower():

            # ✅ STUDENT FOUND
                        total = 0.0
                        marks = {}

                        for sub in subjects:
                            val = row.get(sub)
                            try:
                                score = float(val) if pd.notna(val) else 0.0
                            except:
                                score = 0.0

                            marks[sub] = {
                                "max_marks": tot_marks,
                                "obtained_marks": score
                            }
                            total += score
                        
                        students_db[key].setdefault("tests", {})
                        students_db[key].setdefault("performance", {})

                        students_db[key]["tests"][test_name] = marks

                        max_total = tot_marks * len(subjects)
                        percent = round((total / max_total) * 100, 2)
                        
                        # 🎯 Calculate grade based on percentage
                        grade = calculate_grade(percent)

                        # 📝 Store performance data with grade
                        students_db[key]["performance"][test_name] = {
                            "total_obtained": total,
                            "total_max": max_total,
                            "percentage": percent,
                            "grade": grade  # ✨ Added grade field
                        }

                        await ftp_write(path, students_db)

                        updated_students += 1
                        student_updated = True
                        break  # STOP file loop

                if student_updated:
                    break

            if not student_updated:
                not_found_students.append(student_name)

        # 🔥 Log to Firestore if needed (SAFE)
        if not_found_students and firestore_db:
            try:
                firestore_db.collection("server_info").add({
                    "type": "marks_upload_missing_students",
                    "class_level": class_level,
                    "course": course,
                    "test_name": test_name,
                    "students": not_found_students,
                    "timestamp": datetime.utcnow().isoformat()
                })
            except Exception as e:
                print("⚠️ Firestore logging failed:", e)

        return {
            "status": "success",
            "class": class_level,
            "course": course,
            "test_name": test_name,
            "updated_students": updated_students,
            "not_found_students": not_found_students
        }

    except Exception as e:
        print("UPLOAD ERROR:", e)
        raise HTTPException(500, str(e))

# ========= TIMETABLE SERVICE =========

TIMETABLE_PATH = "htdocs/services/timetable.json"
@app.post("/timetable/upload")
async def upload_timetable(file: UploadFile = File(...)):
    try:
        contents = await file.read()
        # Read without headers to manually parse the structure
        df = pd.read_excel(io.BytesIO(contents), header=None)

        if df.empty:
            raise HTTPException(status_code=400, detail="Empty Excel file")

        # 1️⃣ Detect DAY Safely (e.g., "TUESDAY")
        day = "UNKNOWN"
        for i in range(min(5, len(df))):
            for cell in df.iloc[i]:
                if isinstance(cell, str) and cell.strip():
                    # Captures the first word (Day)
                    day = cell.strip().split()[0].upper() 
                    break
            if day != "UNKNOWN": break

        # 2️⃣ Detect TIME ROW (Where periods are defined)
        time_row_index = None
        times = {} # Column Index -> "Time Range"

        for i in range(min(10, len(df))):
            row = df.iloc[i]
            # Look for cells containing time patterns like "07:30 to 08:30"
            found_times = {col: str(val).strip() for col, val in enumerate(row) 
                           if isinstance(val, str) and ("to" in val.lower() or "-" in val)}
            
            if len(found_times) >= 2:
                time_row_index = i
                times = found_times
                break

        if time_row_index is None:
            raise HTTPException(status_code=400, detail="Time row (e.g., '07:30 to 08:30') not found")

        # 3️⃣ Build Structured JSON
        timetable = {
            "day": day,
            "classes": {}, # Will hold "TUESDAY_1ST_PUC": { "VASISHTHA": [...] }
            "last_updated": datetime.utcnow().isoformat()
        }

        current_puc_class = None

        # Start reading from the row after the time headers
        for i in range(time_row_index + 1, len(df)):
            row = df.iloc[i]
            
            # 🔹 Check if this row is a CLASS HEADER (e.g., "TUESDAY 1ST PUC")
            # We look for "PUC" in the row. If found, all following sections belong to it.
            row_as_string = " ".join([str(c) for c in row if pd.notna(c)])
            if "PUC" in row_as_string.upper():
                # Extract the specific PUC name and format it as a key
                current_puc_class = row_as_string.strip().replace(" ", "_").upper()
                timetable["classes"].setdefault(current_puc_class, {})
                continue

            # 🔹 Identify the SECTION (Usually the first column, e.g., "VASISHTHA")
            section_name = str(row[0]).strip().upper() if pd.notna(row[0]) else None
            
            # Skip rows that don't have a section name or if we haven't found a PUC header yet
            if not section_name or not current_puc_class or section_name == "SECTION":
                continue

            # Initialize the section list
            timetable["classes"][current_puc_class].setdefault(section_name, [])

            # 🔹 Map subjects to times
            for col, time_range in times.items():
                if col < len(row):
                    subject_val = row[col]
                    if pd.notna(subject_val) and str(subject_val).strip():
                        # Clean subject name (remove teacher names in brackets if they exist)
                        subject_name = str(subject_val).split("(")[0].strip().upper()
                        
                        timetable["classes"][current_puc_class][section_name].append({
                            "time": time_range,
                            "subject": subject_name
                        })

        # 4️⃣ Save File
        services_base = BASE_PATH.replace("Database_1", "services")
        await ftp_ensure_dir(services_base)
        path = f"{services_base}/timetable.json"
        await ftp_write(path, timetable)

        return {
            "status": "success",
            "day": day,
            "classes_detected": list(timetable["classes"].keys())
        }

    except Exception as e:
        print(f"UPLOAD ERROR: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Failed to parse Excel: {str(e)}")

@app.get("/timetable")
async def get_timetable():
    try:
        data = await ftp_read(TIMETABLE_PATH)
        return data if data else {"sections": {}}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/timetable/daily")
async def get_daily_timetable(section: str | None = None):
    try:
        file_path = f"{TIMETABLE_PATH}"
        timetable = await ftp_read(file_path)

        if not timetable:
            return {
                "status": "error",
                "message": "Timetable not uploaded"
            }

        if section:
            return {
                "status": "success",
                "section": section,
                "timetable": timetable["sections"].get(section.lower(), [])
            }

        return {
            "status": "success",
            "date": timetable.get("date"),
            "sections": timetable.get("sections", {})
        }

    except Exception as e:
        print("FETCH TIMETABLE ERROR:", e)
        return {
            "status": "error",
            "message": str(e)
        }


# ========= SECTION TRANSFER API =========

@app.post("/students/transfer-section")
async def transfer_students_between_sections(payload: SectionTransferRequest):
    source_file = f"{BASE_PATH}/{payload.source_section}"
    target_file = f"{BASE_PATH}/{payload.target_section}"

    if payload.source_section == payload.target_section:
        raise HTTPException(status_code=400, detail="Source and target sections cannot be the same")

    try:
        source_db = await ftp_read(source_file)
        target_db = await ftp_read(target_file)

        if not source_db:
            raise HTTPException(status_code=404, detail="Source section file not found")

        if target_db is None:
            target_db = {}

        moved_students = []
        skipped_students = []

        for student_name in payload.students:
            key = next(
                (k for k in source_db if k.strip().lower() == student_name.strip().lower()),
                None
            )

            if not key:
                skipped_students.append(student_name)
                continue

            # Avoid duplicate entry in target
            if any(k.strip().lower() == key.strip().lower() for k in target_db):
                skipped_students.append(student_name)
                continue

            # Move student
            target_db[key] = source_db.pop(key)
            moved_students.append(key)

        # Save files only if changes occurred
        if moved_students:
            await ftp_write(source_file, source_db)
            await ftp_write(target_file, target_db)

        # 🔥 Firestore logging (optional but recommended)
        if firestore_db:
            firestore_db.collection("server_info").add({
                "type": "section_transfer",
                "from": payload.source_section,
                "to": payload.target_section,
                "moved_students": moved_students,
                "skipped_students": skipped_students,
                "timestamp": datetime.utcnow().isoformat()
            })

        return {
            "status": "success",
            "from": payload.source_section,
            "to": payload.target_section,
            "moved_count": len(moved_students),
            "moved_students": moved_students,
            "skipped_students": skipped_students
        }

    except HTTPException:
        raise
    except Exception as e:
        print("SECTION TRANSFER ERROR:", str(e))
        raise HTTPException(status_code=500, detail=str(e))


# ========= 🆕 TEACHER NOTICES/MESSAGING API =========

@app.get("/notices/teachers")
async def get_teacher_notices():
    """
    Retrieve all teacher notices from the FTP server.
    Returns the notices in chronological order (newest first).
    """
    try:
        # Ensure the notices directory exists
        await ftp_ensure_dir(NOTICES_BASE_PATH)
        
        # Try to read existing notices
        notices_data = await ftp_read(TEACHERS_NOTICES_PATH)
        
        # If file doesn't exist, initialize with empty structure
        if not notices_data:
            notices_data = {
                "last_updated": datetime.utcnow().isoformat(),
                "notices": []
            }
        
        # Sort notices by timestamp (newest first)
        notices = notices_data.get("notices", [])
        notices.sort(key=lambda x: x.get("timestamp", ""), reverse=True)
        
        return {
            "status": "success",
            "last_updated": notices_data.get("last_updated"),
            "total_notices": len(notices),
            "notices": notices
        }
    
    except Exception as e:
        print("GET NOTICES ERROR:", str(e))
        raise HTTPException(
            status_code=500,
            detail=f"Failed to retrieve notices: {str(e)}"
        )


@app.post("/notices/teachers")
async def create_teacher_notice(notice: NoticeCreateRequest):
    """
    Create a new teacher notice and store it in the FTP server.
    
    Request body:
    - author: Name of the person creating the notice
    - title: Title of the notice
    - content: Main content of the notice
    - urgency: Priority level ("urgent", "medium", "low")
    """
    try:
        # Validate urgency level
        valid_urgency = ["urgent", "medium", "low"]
        if notice.urgency.lower() not in valid_urgency:
            raise HTTPException(
                status_code=400,
                detail=f"Invalid urgency level. Must be one of: {', '.join(valid_urgency)}"
            )
        
        # Ensure the notices directory exists
        await ftp_ensure_dir(NOTICES_BASE_PATH)
        
        # Read existing notices
        notices_data = await ftp_read(TEACHERS_NOTICES_PATH)
        
        # Initialize if file doesn't exist
        if not notices_data:
            notices_data = {
                "last_updated": datetime.utcnow().isoformat(),
                "notices": []
            }
        
        # Generate unique notice ID using timestamp
        notice_id = f"n_{int(datetime.utcnow().timestamp() * 1000)}"
        
        # Create new notice object
        new_notice = {
            "notice_id": notice_id,
            "author": notice.author.strip(),
            "title": notice.title.strip(),
            "content": notice.content.strip(),
            "urgency": notice.urgency.lower(),
            "timestamp": datetime.utcnow().isoformat()
        }
        
        # Add notice to the list
        notices_data["notices"].append(new_notice)
        notices_data["last_updated"] = datetime.utcnow().isoformat()
        
        # Write back to FTP
        await ftp_write(TEACHERS_NOTICES_PATH, notices_data)
        
        # Log to Firestore (optional)
        if firestore_db:
            try:
                firestore_db.collection("server_info").add({
                    "type": "notice_created",
                    "notice_id": notice_id,
                    "author": notice.author,
                    "title": notice.title,
                    "urgency": notice.urgency,
                    "timestamp": datetime.utcnow().isoformat()
                })
            except Exception as e:
                print("⚠️ Firestore logging failed:", e)
        
        return {
            "status": "success",
            "message": "Notice created successfully",
            "notice": new_notice
        }
    
    except HTTPException:
        raise
    except Exception as e:
        print("CREATE NOTICE ERROR:", str(e))
        raise HTTPException(
            status_code=500,
            detail=f"Failed to create notice: {str(e)}"
        )


@app.delete("/notices/teachers/{notice_id}")
async def delete_teacher_notice(notice_id: str):
    """
    Delete a specific teacher notice by its ID.
    """
    try:
        # Read existing notices
        notices_data = await ftp_read(TEACHERS_NOTICES_PATH)
        
        if not notices_data or not notices_data.get("notices"):
            raise HTTPException(
                status_code=404,
                detail="No notices found"
            )
        
        # Find and remove the notice
        notices = notices_data["notices"]
        original_count = len(notices)
        
        notices_data["notices"] = [
            n for n in notices if n.get("notice_id") != notice_id
        ]
        
        # Check if notice was found and deleted
        if len(notices_data["notices"]) == original_count:
            raise HTTPException(
                status_code=404,
                detail=f"Notice with ID '{notice_id}' not found"
            )
        
        # Update last_updated timestamp
        notices_data["last_updated"] = datetime.utcnow().isoformat()
        
        # Write back to FTP
        await ftp_write(TEACHERS_NOTICES_PATH, notices_data)
        
        # Log to Firestore (optional)
        if firestore_db:
            try:
                firestore_db.collection("server_info").add({
                    "type": "notice_deleted",
                    "notice_id": notice_id,
                    "timestamp": datetime.utcnow().isoformat()
                })
            except Exception as e:
                print("⚠️ Firestore logging failed:", e)
        
        return {
            "status": "success",
            "message": f"Notice '{notice_id}' deleted successfully"
        }
    
    except HTTPException:
        raise
    except Exception as e:
        print("DELETE NOTICE ERROR:", str(e))
        raise HTTPException(
            status_code=500,
            detail=f"Failed to delete notice: {str(e)}"
        )


@app.get("/notices/teachers/urgent")
async def get_urgent_teacher_notices():
    """
    Retrieve only urgent teacher notices.
    """
    try:
        notices_data = await ftp_read(TEACHERS_NOTICES_PATH)
        
        if not notices_data:
            return {
                "status": "success",
                "total_urgent": 0,
                "notices": []
            }
        
        # Filter urgent notices
        urgent_notices = [
            n for n in notices_data.get("notices", [])
            if n.get("urgency", "").lower() == "urgent"
        ]
        
        # Sort by timestamp (newest first)
        urgent_notices.sort(key=lambda x: x.get("timestamp", ""), reverse=True)
        
        return {
            "status": "success",
            "total_urgent": len(urgent_notices),
            "notices": urgent_notices
        }
    
    except Exception as e:
        print("GET URGENT NOTICES ERROR:", str(e))
        raise HTTPException(
            status_code=500,
            detail=f"Failed to retrieve urgent notices: {str(e)}"
        )
