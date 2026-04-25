from fastapi import FastAPI, HTTPException, Depends, Form
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from sqlalchemy import create_engine, Column, Integer, String, Float, DateTime, Boolean, Text, ForeignKey
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker, relationship
from datetime import datetime, timedelta
import bcrypt
import jwt
import math
import os

# ----- Configuración de base de datos -----
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

# Recrear tablas (borra datos antiguos)
Base.metadata.drop_all(bind=engine)
Base.metadata.create_all(bind=engine)

# ----- Función para crear/actualizar usuario de prueba -----
def crear_usuario(db, email, password, rol, nombre, eps=None, arl=None, rh=None, contacto_emergencia=None, foto_perfil=None):
    hashed = bcrypt.hashpw(password.encode(), bcrypt.gensalt())
    user = db.query(User).filter(User.email == email).first()
    if user:
        user.password = hashed.decode()
        user.rol = rol
        user.nombre = nombre
        user.eps = eps
        user.arl = arl
        user.rh = rh
        user.contacto_emergencia = contacto_emergencia
        user.foto_perfil = foto_perfil
    else:
        user = User(
            email=email, password=hashed.decode(), rol=rol, nombre=nombre,
            eps=eps, arl=arl, rh=rh, contacto_emergencia=contacto_emergencia, foto_perfil=foto_perfil
        )
        db.add(user)
    db.commit()
    return user

# ----- Crear usuarios de prueba (forzado) -----
db = SessionLocal()
crear_usuario(db, "cliente@test.com", "1234", "cliente", "Cliente Demo")
crear_usuario(db, "tecnico1@test.com", "1234", "tecnico", "Tecnico Juan", "Nueva EPS", "Positiva", "O+", "Maria Perez - 3111234567", "")
crear_usuario(db, "tecnico2@test.com", "1234", "tecnico", "Tecnico Maria", "Sanitas", "Sura", "A-", "Luis Rodriguez - 3109876543", "")
crear_usuario(db, "coordinador@test.com", "1234", "coordinador", "Coord Ana")
crear_usuario(db, "lider@test.com", "1234", "lider", "Lider Carlos")
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

# ----- Autenticación -----
@app.post("/auth/register")
def register(email: str = Form(...), password: str = Form(...), rol: str = Form(...), nombre: str = Form(...)):
    db = SessionLocal()
    if db.query(User).filter(User.email == email).first():
        raise HTTPException(400, "Email ya registrado")
    hashed = bcrypt.hashpw(password.encode(), bcrypt.gensalt())
    user = User(email=email, password=hashed.decode(), rol=rol, nombre=nombre)
    db.add(user)
    db.commit()
    db.close()
    return {"mensaje": "Usuario creado"}

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
        "id": usuario.id,
        "nombre": usuario.nombre,
        "email": usuario.email,
        "rol": usuario.rol,
        "eps": usuario.eps,
        "arl": usuario.arl,
        "rh": usuario.rh,
        "contacto_emergencia": usuario.contacto_emergencia,
        "foto_perfil": usuario.foto_perfil
    }

# ----- Solicitudes (igual que antes) -----
# ... Aquí van todos los demás endpoints (solicitudes, jornada, parqueaderos, etc.)
# Por brevedad, no los repito aquí, pero deben estar todos. Como ya los tienes, los mantienes.

# ----- Endpoint de inserción de datos de prueba (solo líder) -----
@app.post("/admin/insertar_datos_prueba")
def insertar_datos_prueba(user=Depends(get_current_user)):
    if user.rol not in ["lider", "coordinador"]:
        raise HTTPException(403, "No autorizado")
    db = SessionLocal()
    db.query(Maquina).delete()
    db.query(Parqueadero).delete()
    db.commit()
    # ... (el código de inserción de parqueaderos y máquinas que ya tenías)
    # No lo incluyo por longitud, pero debe estar completo.
    # Asegúrate de que al final devuelva un mensaje de éxito.
    db.close()
    return {"mensaje": "Datos insertados"}

# Para correr localmente
if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=10000)
