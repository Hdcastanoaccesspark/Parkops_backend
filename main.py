from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

# Importa los routers que ya tenías creados (ajusta las rutas si los tienes en otra carpeta)
from routers import auth
from routers import users
from routers import parqueaderos
from routers import maquinas
from routers import solicitudes
from routers import admin

app = FastAPI(
    title="ParkOps Backend",
    description="API de soporte técnico Accespark",
    version="1.0.0"
)

# CORS para permitir peticiones desde la app Flutter
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Incluir los routers con sus prefijos
app.include_router(auth.router, prefix="/auth", tags=["Autenticación"])
app.include_router(users.router, prefix="/usuarios", tags=["Usuarios"])
app.include_router(parqueaderos.router, prefix="/parqueaderos", tags=["Parqueaderos"])
app.include_router(maquinas.router, prefix="/maquinas", tags=["Máquinas"])
app.include_router(solicitudes.router, prefix="/solicitudes", tags=["Solicitudes"])
app.include_router(admin.router, prefix="/admin", tags=["Admin"])

@app.get("/")
def root():
    return {"mensaje": "ParkOps Backend funcionando"}
