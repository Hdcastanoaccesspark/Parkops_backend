from fastapi import FastAPI, HTTPException, Depends, Form, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from fastapi.responses import FileResponse, JSONResponse
from sqlalchemy import create_engine, Column, Integer, String, Float, DateTime, Boolean, Text, ForeignKey
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker
from datetime import datetime, timedelta
import bcrypt
import jwt
import math
import os
import traceback
from fpdf import FPDF

# ----- Base de datos -----
engine = create_engine('sqlite:///parkops.db', connect_args={'check_same_thread': False})
SessionLocal = sessionmaker(bind=engine)
Base = declarative_base()

# ----- Modelos -----
class User(Base):
    __tablename__ = 'users'
    id = Column(Integer, primary_key=True)
    email = Column(String, unique=True)
    password = Column(String)
    rol = Column(String)
    nombre = Column(String)
    lat = Column(Float, nullable=True)
    lon = Column(Float, nullable=True)
    estado = Column(String, default='libre')
    disponible = Column(Boolean, default=False)
    eps = Column(String, nullable=True)
    arl = Column(String, nullable=True)
    rh = Column(String, nullable=True)
    contacto_emergencia = Column(String, nullable=True)
    foto_perfil = Column(Text, nullable=True)

class Solicitud(Base):
    __tablename__ = 'solicitudes'
    id = Column(Integer, primary_key=True)
    cliente_id = Column(Integer)
    descripcion = Column(Text)
    lat = Column(Float)
    lon = Column(Float)
    tipo = Column(String)
    estado = Column(String)
    tecnico_id = Column(Integer, nullable=True)
    maquina_id = Column(Integer, nullable=True)
    solicitud_original_id = Column(Integer, nullable=True)   # NUEVO
    fecha_creacion = Column(DateTime, default=datetime.utcnow)
    fecha_asignacion = Column(DateTime, nullable=True)
    fecha_aceptacion = Column(DateTime, nullable=True)
    fecha_inicio = Column(DateTime, nullable=True)
    fecha_fin = Column(DateTime, nullable=True)
    fotos = Column(Text, nullable=True)
    videos = Column(Text, nullable=True)
    items = Column(Text, nullable=True)
    firma = Column(Text, nullable=True)

class Jornada(Base):
    __tablename__ = 'jornadas'
    id = Column(Integer, primary_key=True)
    tecnico_id = Column(Integer)
    inicio = Column(DateTime)
    fin = Column(DateTime, nullable=True)
    lat_inicio = Column(Float)
    lon_inicio = Column(Float)
    lat_fin = Column(Float, nullable=True)
    lon_fin = Column(Float, nullable=True)

class Parqueadero(Base):
    __tablename__ = 'parqueaderos'
    id = Column(Integer, primary_key=True)
    nombre = Column(String)
    direccion = Column(String)
    lat = Column(Float)
    lon = Column(Float)
    ciudad = Column(String)

class Maquina(Base):
    __tablename__ = 'maquinas'
    id = Column(Integer, primary_key=True)
    codigo_qr = Column(String, unique=True)
    nombre = Column(String)
    tipo = Column(String)
    parqueadero_id = Column(Integer, ForeignKey('parqueaderos.id'))
    lat = Column(Float, nullable=True)
    lon = Column(Float, nullable=True)

Base.metadata.create_all(bind=engine)

def seed_database():
    db = SessionLocal()
    try:
        if db.query(User).count() == 0:
            usuarios = [
                {"email": "cliente@test.com", "password": "1234", "rol": "cliente", "nombre": "Cliente Demo"},
                {"email": "tecnico1@test.com", "password": "1234", "rol": "tecnico", "nombre": "Tecnico Juan", "eps": "Nueva EPS", "arl": "Positiva", "rh": "O+", "contacto_emergencia": "Maria Perez - 3111234567"},
                {"email": "tecnico2@test.com", "password": "1234", "rol": "tecnico", "nombre": "Tecnico Maria", "eps": "Sanitas", "arl": "Sura", "rh": "A-", "contacto_emergencia": "Luis Rodriguez - 3109876543"},
                {"email": "coordinador@test.com", "password": "1234", "rol": "coordinador", "nombre": "Coord Ana"},
                {"email": "lider@test.com", "password": "1234", "rol": "lider", "nombre": "Lider Carlos"},
            ]
            for u in usuarios:
                hashed = bcrypt.hashpw(u["password"].encode(), bcrypt.gensalt())
                db.add(User(email=u["email"], password=hashed.decode(), rol=u["rol"], nombre=u["nombre"],
                            eps=u.get("eps"), arl=u.get("arl"), rh=u.get("rh"), contacto_emergencia=u.get("contacto_emergencia")))
            db.commit()

        if db.query(Parqueadero).count() == 0:
            p1 = Parqueadero(nombre="Parqueadero Centro", direccion="Calle 19 # 5-30", lat=4.598, lon=-74.071, ciudad="Bogotá")
            p2 = Parqueadero(nombre="Centro Comercial Unicentro", direccion="Cra 68 # 90-12", lat=4.676, lon=-74.077, ciudad="Bogotá")
            p3 = Parqueadero(nombre="Parqueadero El Dorado", direccion="Av. El Dorado", lat=4.701, lon=-74.146, ciudad="Bogotá")
            p4 = Parqueadero(nombre="Parqueadero Chapinero", direccion="Calle 45 # 15-80", lat=4.641, lon=-74.065, ciudad="Bogotá")
            p5 = Parqueadero(nombre="Parqueadero Salitre", direccion="Calle 24 # 60-10", lat=4.653, lon=-74.104, ciudad="Bogotá")
            db.add_all([p1, p2, p3, p4, p5])
            db.commit()
            # ... (máquinas igual que antes, copia el bloque completo de máquinas del main.py anterior)
    except Exception as e:
        print(f"Error seeding database: {e}")
        db.rollback()
    finally:
        db.close()

seed_database()

app = FastAPI(title="ParkOps API")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_credentials=True, allow_methods=["*"], allow_headers=["*"])

SECRET_KEY = "clave_super_secreta_parkops"
security = HTTPBearer()

def get_current_user(credentials: HTTPAuthorizationCredentials = Depends(security)):
    try:
        payload = jwt.decode(credentials.credentials, SECRET_KEY, algorithms=['HS256'])
        db = SessionLocal()
        user = db.query(User).filter(User.id == payload['user_id']).first()
        db.close()
        return user
    except:
        raise HTTPException(401, "Token inválido")

def distancia(lat1, lon1, lat2, lon2):
    return math.sqrt((lat1-lat2)**2 + (lon1-lon2)**2)

# ---------- Endpoints ----------
@app.get("/")
def root():
    return {"mensaje": "ParkOps API funcionando"}

@app.post("/auth/login")
def login(email: str = Form(...), password: str = Form(...)):
    db = SessionLocal()
    user = db.query(User).filter(User.email == email).first()
    db.close()
    if not user or not bcrypt.checkpw(password.encode(), user.password.encode()):
        raise HTTPException(401, "Credenciales incorrectas")
    token = jwt.encode({"user_id": user.id, "rol": user.rol, "exp": datetime.utcnow() + timedelta(hours=24)}, SECRET_KEY)
    return {"token": token, "rol": user.rol, "user_id": user.id}

@app.get("/usuarios/{user_id}")
def get_usuario(user_id: int, user=Depends(get_current_user)):
    if user.id != user_id and user.rol not in ['lider', 'coordinador']:
        raise HTTPException(403, "No autorizado")
    db = SessionLocal()
    usuario = db.query(User).filter(User.id == user_id).first()
    db.close()
    if not usuario:
        raise HTTPException(404, "Usuario no encontrado")
    return {
        "id": usuario.id, "nombre": usuario.nombre, "email": usuario.email, "rol": usuario.rol,
        "eps": usuario.eps, "arl": usuario.arl, "rh": usuario.rh,
        "contacto_emergencia": usuario.contacto_emergencia, "foto_perfil": usuario.foto_perfil
    }

@app.post("/solicitudes/crear")
def crear_solicitud(
    descripcion: str = Form(...),
    lat: float = Form(...),
    lon: float = Form(...),
    tipo: str = Form(...),
    fotos: str = Form(""),
    videos: str = Form(""),
    maquina_id: str = Form(None),
    solicitud_original_id: str = Form(None),   # NUEVO
    user=Depends(get_current_user)
):
    try:
        if user.rol not in ['cliente', 'tecnico']:
            raise HTTPException(403, "No autorizado")
        db = SessionLocal()
        tecnicos = db.query(User).filter(User.rol == 'tecnico', User.disponible == True).all()
        if tecnicos:
            tecnico = min(tecnicos, key=lambda t: distancia(lat, lon, t.lat or 0, t.lon or 0))
            estado = 'asignada'
            fecha_asignacion = datetime.utcnow()
        else:
            tecnico = None
            estado = 'pendiente'
            fecha_asignacion = None
        maq_id = None
        if maquina_id and maquina_id.strip() and maquina_id not in ('None', 'null', ''):
            try:
                maq_id = int(maquina_id)
            except:
                pass
        original_id = None
        if solicitud_original_id and solicitud_original_id.strip() and solicitud_original_id not in ('None', 'null', ''):
            try:
                original_id = int(solicitud_original_id)
            except:
                pass
        solicitud = Solicitud(
            cliente_id=user.id, descripcion=descripcion, lat=lat, lon=lon, tipo=tipo,
            estado=estado, tecnico_id=tecnico.id if tecnico else None,
            maquina_id=maq_id, fecha_asignacion=fecha_asignacion,
            fotos=fotos, videos=videos,
            solicitud_original_id=original_id
        )
        db.add(solicitud)
        db.commit()
        db.refresh(solicitud)
        db.close()
        return {"mensaje": "Solicitud creada", "tecnico": tecnico.nombre if tecnico else "Pendiente de asignación", "solicitud_id": solicitud.id}
    except HTTPException:
        raise
    except Exception as e:
        traceback.print_exc()
        raise HTTPException(500, f"Error al crear solicitud: {str(e)}")

@app.get("/api/solicitudes")
def listar_solicitudes(user=Depends(get_current_user)):
    try:
        db = SessionLocal()
        if user.rol == 'cliente':
            solicitudes = db.query(Solicitud).filter(Solicitud.cliente_id == user.id).all()
        elif user.rol == 'tecnico':
            solicitudes = db.query(Solicitud).filter(Solicitud.tecnico_id == user.id).all()
        else:
            solicitudes = db.query(Solicitud).all()
        db.close()
        result = []
        for s in solicitudes:
            cliente_nombre = None
            if s.cliente_id:
                db2 = SessionLocal()
                cliente = db2.query(User).filter(User.id == s.cliente_id).first()
                if cliente: cliente_nombre = cliente.nombre
                db2.close()
            result.append({"id": s.id, "descripcion": s.descripcion, "estado": s.estado, "tipo": s.tipo, "cliente_nombre": cliente_nombre})
        return result
    except Exception as e:
        traceback.print_exc()
        raise HTTPException(500, str(e))

@app.post("/tecnico/iniciar_jornada")
def iniciar_jornada(lat: float = Form(...), lon: float = Form(...), user=Depends(get_current_user)):
    try:
        if user.rol != 'tecnico': raise HTTPException(403, "No autorizado")
        db = SessionLocal()
        if db.query(Jornada).filter(Jornada.tecnico_id == user.id, Jornada.fin == None).first():
            db.close(); raise HTTPException(400, "Ya hay jornada activa")
        nueva = Jornada(tecnico_id=user.id, inicio=datetime.utcnow(), lat_inicio=lat, lon_inicio=lon)
        user.disponible = True; user.lat, user.lon = lat, lon
        db.add(nueva); db.commit(); db.close()
        return {"mensaje": "Jornada iniciada"}
    except HTTPException:
        raise
    except Exception as e:
        traceback.print_exc()
        raise HTTPException(500, str(e))

@app.post("/tecnico/finalizar_jornada")
def finalizar_jornada(lat: float = Form(...), lon: float = Form(...), user=Depends(get_current_user)):
    try:
        if user.rol != 'tecnico': raise HTTPException(403, "No autorizado")
        db = SessionLocal()
        jornada = db.query(Jornada).filter(Jornada.tecnico_id == user.id, Jornada.fin == None).first()
        if not jornada: db.close(); raise HTTPException(404, "No hay jornada activa")
        jornada.fin = datetime.utcnow(); jornada.lat_fin, jornada.lon_fin = lat, lon
        user.disponible = False; db.commit(); db.close()
        return {"mensaje": "Jornada finalizada"}
    except HTTPException:
        raise
    except Exception as e:
        traceback.print_exc()
        raise HTTPException(500, str(e))

@app.post("/tecnico/aceptar/{solicitud_id}")
def aceptar_solicitud(solicitud_id: int, user=Depends(get_current_user)):
    try:
        if user.rol != 'tecnico': raise HTTPException(403)
        db = SessionLocal()
        solicitud = db.query(Solicitud).filter(Solicitud.id == solicitud_id, Solicitud.tecnico_id == user.id).first()
        if not solicitud or solicitud.estado not in ['asignada', 'pendiente']:
            db.close(); raise HTTPException(404, "Solicitud no válida")
        solicitud.estado = 'aceptada'; solicitud.tecnico_id = user.id
        solicitud.fecha_aceptacion = datetime.utcnow()
        user.estado = 'ocupado'; db.commit(); db.close()
        return {"mensaje": "Solicitud aceptada"}
    except HTTPException:
        raise
    except Exception as e:
        traceback.print_exc()
        raise HTTPException(500, str(e))

@app.post("/tecnico/iniciar_servicio/{solicitud_id}")
def iniciar_servicio(solicitud_id: int, lat: float = Form(...), lon: float = Form(...), user=Depends(get_current_user)):
    try:
        if user.rol != 'tecnico': raise HTTPException(403)
        db = SessionLocal()
        solicitud = db.query(Solicitud).filter(Solicitud.id == solicitud_id, Solicitud.tecnico_id == user.id).first()
        if not solicitud or solicitud.estado != 'aceptada':
            db.close(); raise HTTPException(404)
        solicitud.estado = 'en_proceso'; solicitud.fecha_inicio = datetime.utcnow()
        user.estado = 'en_servicio'; db.commit(); db.close()
        return {"mensaje": "Servicio iniciado"}
    except HTTPException:
        raise
    except Exception as e:
        traceback.print_exc()
        raise HTTPException(500, str(e))

@app.post("/tecnico/cerrar_solicitud/{solicitud_id}")
def cerrar_solicitud(solicitud_id: int, items: str = Form(...), firma: str = Form(...), user=Depends(get_current_user)):
    try:
        if user.rol != 'tecnico': raise HTTPException(403)
        db = SessionLocal()
        solicitud = db.query(Solicitud).filter(Solicitud.id == solicitud_id, Solicitud.tecnico_id == user.id).first()
        if not solicitud or solicitud.estado != 'en_proceso':
            db.close(); raise HTTPException(404)
        solicitud.estado = 'finalizada'; solicitud.items = items; solicitud.firma = firma
        solicitud.fecha_fin = datetime.utcnow(); user.estado = 'libre'
        db.commit()
        # Generar PDF (incluye solicitud original si existe)
        try:
            pdf_path = generar_pdf(solicitud_id)
            cliente = db.query(User).filter(User.id == solicitud.cliente_id).first()
            if cliente:
                print(f"📧 PDF generado para {cliente.email}")
        except:
            traceback.print_exc()
        db.close()
        return {"mensaje": "Servicio finalizado, PDF generado"}
    except HTTPException:
        raise
    except Exception as e:
        traceback.print_exc()
        raise HTTPException(500, str(e))

def generar_pdf(solicitud_id: int):
    db = SessionLocal()
    solicitud = db.query(Solicitud).filter(Solicitud.id == solicitud_id).first()
    if not solicitud:
        db.close()
        raise HTTPException(404, "Solicitud no encontrada")
    cliente = db.query(User).filter(User.id == solicitud.cliente_id).first()
    tecnico = db.query(User).filter(User.id == solicitud.tecnico_id).first() if solicitud.tecnico_id else None

    # Si existe solicitud original, agregamos su información
    desc_original = ""
    if solicitud.solicitud_original_id:
        original = db.query(Solicitud).filter(Solicitud.id == solicitud.solicitud_original_id).first()
        if original:
            desc_original = original.descripcion
    db.close()

    pdf = FPDF()
    pdf.add_page()
    pdf.set_font("Arial", size=12)
    pdf.cell(200, 10, txt="ParkOps - Reporte de Servicio", ln=True, align='C')
    pdf.ln(10)
    pdf.set_font("Arial", size=10)
    pdf.cell(200, 8, txt=f"ID Solicitud: {solicitud_id}", ln=True)
    if desc_original:
        pdf.cell(200, 8, txt=f"Problema reportado: {desc_original[:150]}...", ln=True)
    pdf.cell(200, 8, txt=f"Cliente: {cliente.nombre if cliente else 'N/A'}", ln=True)
    pdf.cell(200, 8, txt=f"Tecnico: {tecnico.nombre if tecnico else 'N/A'}", ln=True)
    pdf.cell(200, 8, txt=f"Tipo: {solicitud.tipo}", ln=True)
    pdf.cell(200, 8, txt=f"Descripcion tecnico: {solicitud.descripcion[:150]}...", ln=True)
    pdf.cell(200, 8, txt=f"Estado: {solicitud.estado}", ln=True)
    pdf.cell(200, 8, txt=f"Fecha: {solicitud.fecha_creacion} a {solicitud.fecha_fin}", ln=True)
    if solicitud.firma:
        pdf.ln(5)
        pdf.cell(200, 8, txt="Firma digital registrada", ln=True)
    pdf.output(f"/tmp/solicitud_{solicitud_id}.pdf")
    return f"/tmp/solicitud_{solicitud_id}.pdf"

@app.get("/reporte/{solicitud_id}/pdf")
def descargar_pdf(solicitud_id: int, user=Depends(get_current_user)):
    pdf_path = generar_pdf(solicitud_id)
    return FileResponse(pdf_path, media_type='application/pdf', filename=f'reporte_{solicitud_id}.pdf')

# ... (resto de endpoints: parqueaderos, maquinas, tecnicos, asignar, cancelar, etc.) ...
# COPIA TAL CUAL los endpoints restantes del main.py anterior, incluyendo los de admin y los GET de parqueaderos, etc.

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=10000)
