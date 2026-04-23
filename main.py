from fastapi import FastAPI, HTTPException, Depends, Form
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from sqlalchemy import create_engine, Column, Integer, String, Float, DateTime, Boolean, Text
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker
from datetime import datetime, timedelta
import bcrypt
import jwt
import math
import os

# ----- Configuración de base de datos (usará archivo local en Render) -----
# Render te da un disco temporal, pero para datos persistentes puedes usar PostgreSQL (opcional).
# Por simplicidad, usaremos SQLite (los datos se perderán si Render reinicia el servicio, pero para la demo sirve).
# Si quieres persistencia real, después podemos migrar a PostgreSQL de Render (gratis).
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
    fecha_creacion = Column(DateTime, default=datetime.utcnow)
    fecha_asignacion = Column(DateTime, nullable=True)
    fecha_aceptacion = Column(DateTime, nullable=True)
    fecha_inicio = Column(DateTime, nullable=True)
    fecha_fin = Column(DateTime, nullable=True)
    fotos = Column(Text, nullable=True)
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

Base.metadata.create_all(bind=engine)

# ----- Crear usuarios de prueba (si no existen) -----
db = SessionLocal()
usuarios = [
    {"email": "cliente@test.com", "password": "1234", "rol": "cliente", "nombre": "Cliente Demo"},
    {"email": "tecnico1@test.com", "password": "1234", "rol": "tecnico", "nombre": "Tecnico Juan"},
    {"email": "tecnico2@test.com", "password": "1234", "rol": "tecnico", "nombre": "Tecnico Maria"},
    {"email": "coordinador@test.com", "password": "1234", "rol": "coordinador", "nombre": "Coord Ana"},
    {"email": "lider@test.com", "password": "1234", "rol": "lider", "nombre": "Lider Carlos"},
]
for u in usuarios:
    if not db.query(User).filter(User.email == u["email"]).first():
        hashed = bcrypt.hashpw(u["password"].encode(), bcrypt.gensalt())
        db.add(User(email=u["email"], password=hashed.decode(), rol=u["rol"], nombre=u["nombre"]))
db.commit()
db.close()

# ----- FastAPI app -----
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

@app.post("/solicitudes/crear")
def crear_solicitud(descripcion: str = Form(...), lat: float = Form(...), lon: float = Form(...), tipo: str = Form(...), fotos: str = Form(""), user=Depends(get_current_user)):
    if user.rol != 'cliente':
        raise HTTPException(403, "Solo clientes")
    db = SessionLocal()
    tecnicos = db.query(User).filter(User.rol == 'tecnico', User.disponible == True).all()
    if not tecnicos:
        db.close()
        raise HTTPException(404, "No hay técnicos disponibles")
    tecnico = min(tecnicos, key=lambda t: distancia(lat, lon, t.lat or 0, t.lon or 0))
    solicitud = Solicitud(
        cliente_id=user.id, descripcion=descripcion, lat=lat, lon=lon, tipo=tipo, estado='asignada',
        tecnico_id=tecnico.id, fecha_asignacion=datetime.utcnow(), fotos=fotos
    )
    db.add(solicitud)
    db.commit()
    db.close()
    return {"mensaje": "Solicitud creada", "tecnico": tecnico.nombre, "solicitud_id": solicitud.id}

@app.get("/api/solicitudes")
def listar_solicitudes(user=Depends(get_current_user)):
    db = SessionLocal()
    if user.rol == 'cliente':
        solicitudes = db.query(Solicitud).filter(Solicitud.cliente_id == user.id).all()
    elif user.rol == 'tecnico':
        solicitudes = db.query(Solicitud).filter(Solicitud.tecnico_id == user.id).all()
    else:
        solicitudes = db.query(Solicitud).all()
    db.close()
    return [{"id": s.id, "descripcion": s.descripcion, "estado": s.estado, "tipo": s.tipo} for s in solicitudes]

@app.post("/tecnico/iniciar_jornada")
def iniciar_jornada(lat: float = Form(...), lon: float = Form(...), user=Depends(get_current_user)):
    if user.rol != 'tecnico':
        raise HTTPException(403, "No autorizado")
    db = SessionLocal()
    activa = db.query(Jornada).filter(Jornada.tecnico_id == user.id, Jornada.fin == None).first()
    if activa:
        db.close()
        raise HTTPException(400, "Ya hay jornada activa")
    nueva = Jornada(tecnico_id=user.id, inicio=datetime.utcnow(), lat_inicio=lat, lon_inicio=lon)
    user.disponible = True
    user.lat, user.lon = lat, lon
    db.add(nueva)
    db.commit()
    db.close()
    return {"mensaje": "Jornada iniciada"}

@app.post("/tecnico/finalizar_jornada")
def finalizar_jornada(lat: float = Form(...), lon: float = Form(...), user=Depends(get_current_user)):
    if user.rol != 'tecnico':
        raise HTTPException(403, "No autorizado")
    db = SessionLocal()
    jornada = db.query(Jornada).filter(Jornada.tecnico_id == user.id, Jornada.fin == None).first()
    if not jornada:
        db.close()
        raise HTTPException(404, "No hay jornada activa")
    jornada.fin = datetime.utcnow()
    jornada.lat_fin, jornada.lon_fin = lat, lon
    user.disponible = False
    db.commit()
    db.close()
    return {"mensaje": "Jornada finalizada"}

@app.post("/tecnico/aceptar/{solicitud_id}")
def aceptar_solicitud(solicitud_id: int, user=Depends(get_current_user)):
    if user.rol != 'tecnico':
        raise HTTPException(403, "No autorizado")
    db = SessionLocal()
    solicitud = db.query(Solicitud).filter(Solicitud.id == solicitud_id, Solicitud.tecnico_id == user.id).first()
    if not solicitud or solicitud.estado != 'asignada':
        db.close()
        raise HTTPException(404, "Solicitud no válida")
    solicitud.estado = 'aceptada'
    solicitud.fecha_aceptacion = datetime.utcnow()
    user.estado = 'ocupado'
    db.commit()
    db.close()
    return {"mensaje": "Solicitud aceptada"}

@app.post("/tecnico/iniciar_servicio/{solicitud_id}")
def iniciar_servicio(solicitud_id: int, lat: float = Form(...), lon: float = Form(...), user=Depends(get_current_user)):
    if user.rol != 'tecnico':
        raise HTTPException(403, "No autorizado")
    db = SessionLocal()
    solicitud = db.query(Solicitud).filter(Solicitud.id == solicitud_id, Solicitud.tecnico_id == user.id).first()
    if not solicitud or solicitud.estado != 'aceptada':
        db.close()
        raise HTTPException(404, "Solicitud no aceptada")
    solicitud.estado = 'en_proceso'
    solicitud.fecha_inicio = datetime.utcnow()
    user.estado = 'en_servicio'
    db.commit()
    db.close()
    return {"mensaje": "Servicio iniciado"}

@app.post("/tecnico/cerrar_solicitud/{solicitud_id}")
def cerrar_solicitud(solicitud_id: int, items: str = Form(...), firma: str = Form(...), user=Depends(get_current_user)):
    if user.rol != 'tecnico':
        raise HTTPException(403, "No autorizado")
    db = SessionLocal()
    solicitud = db.query(Solicitud).filter(Solicitud.id == solicitud_id, Solicitud.tecnico_id == user.id).first()
    if not solicitud or solicitud.estado != 'en_proceso':
        db.close()
        raise HTTPException(404, "Solicitud no en proceso")
    solicitud.estado = 'finalizada'
    solicitud.items = items
    solicitud.firma = firma
    solicitud.fecha_fin = datetime.utcnow()
    user.estado = 'libre'
    db.commit()
    db.close()
    return {"mensaje": "Servicio finalizado"}

# Para correr localmente (útil para pruebas, pero Render usará uvicorn command)
if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=10000)
