import os
import subprocess
import psutil
import json
import time
from datetime import datetime
from typing import Optional
from fastapi import FastAPI, HTTPException, UploadFile, File
from fastapi.responses import JSONResponse, FileResponse
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
import uvicorn

app = FastAPI(
    title="Code Runner - منصة تشغيل الأكواد",
    description="منصة مجانية لتشغيل الأكواد البرمجية بشكل دائم 24/7",
    version="1.0.0"
)

# إضافة CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# قاموس لتخزين العمليات الجارية
RUNNING_PROCESSES = {}
SCRIPTS_DIR = "/home/ubuntu/uploaded_scripts"
LOGS_DIR = "/home/ubuntu/script_logs"

# إنشاء المجلدات إذا لم تكن موجودة
os.makedirs(SCRIPTS_DIR, exist_ok=True)
os.makedirs(LOGS_DIR, exist_ok=True)

# ===================== API Endpoints =====================

@app.get("/")
async def root():
    """الصفحة الرئيسية."""
    return {
        "name": "Code Runner Dashboard",
        "version": "1.0.0",
        "description": "منصة تشغيل الأكواد البرمجية بشكل دائم",
        "endpoints": {
            "upload_script": "POST /upload",
            "start_script": "POST /start/{script_name}",
            "stop_script": "POST /stop/{script_name}",
            "list_scripts": "GET /scripts",
            "get_status": "GET /status/{script_name}",
            "get_logs": "GET /logs/{script_name}",
            "health": "GET /health"
        }
    }

@app.get("/health")
async def health_check():
    """فحص صحة الخادم."""
    return {
        "status": "healthy",
        "timestamp": datetime.now().isoformat(),
        "running_processes": len(RUNNING_PROCESSES)
    }

@app.post("/upload")
async def upload_script(file: UploadFile = File(...)):
    """رفع ملف كود جديد."""
    try:
        script_path = os.path.join(SCRIPTS_DIR, file.filename)
        with open(script_path, "wb") as f:
            content = await file.read()
            f.write(content)
        
        return {
            "message": "تم رفع الملف بنجاح",
            "filename": file.filename,
            "path": script_path,
            "size": len(content),
            "timestamp": datetime.now().isoformat()
        }
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"خطأ في الرفع: {str(e)}")

@app.post("/start/{script_name}")
async def start_script(script_name: str):
    """تشغيل سكريبت."""
    script_path = os.path.join(SCRIPTS_DIR, script_name)
    
    if not os.path.exists(script_path):
        raise HTTPException(status_code=404, detail="الملف غير موجود")
    
    if script_name in RUNNING_PROCESSES:
        return {
            "message": "السكريبت قيد التشغيل بالفعل",
            "script_name": script_name,
            "pid": RUNNING_PROCESSES[script_name]["pid"]
        }
    
    try:
        log_file = os.path.join(LOGS_DIR, f"{script_name}.log")
        
        process = subprocess.Popen(
            ["python3", script_path],
            stdout=open(log_file, 'a'),
            stderr=subprocess.STDOUT,
            preexec_fn=os.setsid
        )
        
        RUNNING_PROCESSES[script_name] = {
            "pid": process.pid,
            "start_time": datetime.now().isoformat(),
            "log_file": log_file
        }
        
        return {
            "message": "تم تشغيل السكريبت بنجاح",
            "script_name": script_name,
            "pid": process.pid,
            "timestamp": datetime.now().isoformat()
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"خطأ في التشغيل: {str(e)}")

@app.post("/stop/{script_name}")
async def stop_script(script_name: str):
    """إيقاف سكريبت."""
    if script_name not in RUNNING_PROCESSES:
        raise HTTPException(status_code=404, detail="السكريبت غير مشغل")
    
    try:
        process_info = RUNNING_PROCESSES[script_name]
        pid = process_info["pid"]
        
        # إيقاف العملية بشكل آمن
        os.killpg(os.getpgid(pid), 9)
        del RUNNING_PROCESSES[script_name]
        
        return {
            "message": "تم إيقاف السكريبت",
            "script_name": script_name,
            "timestamp": datetime.now().isoformat()
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"خطأ في الإيقاف: {str(e)}")

@app.get("/scripts")
async def list_scripts():
    """قائمة بجميع الملفات المرفوعة."""
    scripts = []
    for filename in os.listdir(SCRIPTS_DIR):
        if filename.endswith(".py"):
            filepath = os.path.join(SCRIPTS_DIR, filename)
            scripts.append({
                "name": filename,
                "size": os.path.getsize(filepath),
                "created": datetime.fromtimestamp(os.path.getctime(filepath)).isoformat(),
                "is_running": filename in RUNNING_PROCESSES
            })
    
    return {
        "total": len(scripts),
        "scripts": scripts,
        "timestamp": datetime.now().isoformat()
    }

@app.get("/status/{script_name}")
async def get_status(script_name: str):
    """الحصول على حالة السكريبت."""
    if script_name not in RUNNING_PROCESSES:
        return {
            "script_name": script_name,
            "status": "stopped",
            "timestamp": datetime.now().isoformat()
        }
    
    process_info = RUNNING_PROCESSES[script_name]
    try:
        process = psutil.Process(process_info["pid"])
        return {
            "script_name": script_name,
            "status": "running",
            "pid": process_info["pid"],
            "start_time": process_info["start_time"],
            "cpu_percent": process.cpu_percent(interval=1),
            "memory_mb": process.memory_info().rss / 1024 / 1024,
            "timestamp": datetime.now().isoformat()
        }
    except:
        return {
            "script_name": script_name,
            "status": "error",
            "message": "لا يمكن الوصول للعملية",
            "timestamp": datetime.now().isoformat()
        }

@app.get("/logs/{script_name}")
async def get_logs(script_name: str, lines: int = 50):
    """الحصول على سجلات السكريبت."""
    if script_name in RUNNING_PROCESSES:
        log_file = RUNNING_PROCESSES[script_name]["log_file"]
    else:
        log_file = os.path.join(LOGS_DIR, f"{script_name}.log")
    
    if not os.path.exists(log_file):
        return {
            "script_name": script_name,
            "logs": "لا توجد سجلات بعد",
            "timestamp": datetime.now().isoformat()
        }
    
    try:
        with open(log_file, 'r') as f:
            all_lines = f.readlines()
            recent_lines = all_lines[-lines:]
        
        return {
            "script_name": script_name,
            "logs": "".join(recent_lines),
            "total_lines": len(all_lines),
            "timestamp": datetime.now().isoformat()
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"خطأ في قراءة السجلات: {str(e)}")

@app.get("/dashboard")
async def dashboard():
    """لوحة التحكم - معلومات عامة."""
    running_count = len(RUNNING_PROCESSES)
    all_scripts = []
    
    for filename in os.listdir(SCRIPTS_DIR):
        if filename.endswith(".py"):
            all_scripts.append({
                "name": filename,
                "status": "running" if filename in RUNNING_PROCESSES else "stopped"
            })
    
    return {
        "total_scripts": len(all_scripts),
        "running_scripts": running_count,
        "scripts": all_scripts,
        "server_time": datetime.now().isoformat()
    }

@app.post("/restart-all")
async def restart_all():
    """إعادة تشغيل جميع السكريبتات."""
    restarted = []
    for script_name in list(RUNNING_PROCESSES.keys()):
        try:
            await stop_script(script_name)
            time.sleep(1)
            result = await start_script(script_name)
            restarted.append(script_name)
        except:
            pass
    
    return {
        "message": "تمت إعادة التشغيل",
        "restarted": restarted,
        "timestamp": datetime.now().isoformat()
    }

if __name__ == "__main__":
    uvicorn.run(
        app,
        host="0.0.0.0",
        port=int(os.getenv("PORT", 8000)),
        log_level="info"
    )
