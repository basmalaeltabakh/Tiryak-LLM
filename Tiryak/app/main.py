from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.api import routes_documents, routes_query, routes_summary, routes_entities, routes_voice, routes_evaluation, routes_prescription
from app.startup_seed import ensure_seed_documents_loaded
from app.advanced.egypt_drug_database import preload_egyptian_drug_database
app = FastAPI(
    title="Tiryak API",
    description="API for Tiryak, a clinical guideline assistant for medication safety and drug interaction guidance.",
    version="0.2.0"
)


@app.on_event("startup")
async def load_seed_documents():
    ensure_seed_documents_loaded()
    preload_egyptian_drug_database()




app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/")
def root():
    return {"message": "Tiryak API is running", "status": "ok"}


@app.get("/health")
def health_check():
    return {"status": "healthy"}


app.include_router(routes_documents.router, prefix="/documents", tags=["Documents"])
app.include_router(routes_query.router, prefix="/query", tags=["Query"])
app.include_router(routes_summary.router, prefix="/summary", tags=["Summary"])
app.include_router(routes_entities.router, prefix="/extract", tags=["Extraction"])
app.include_router(routes_voice.router, prefix="/voice", tags=["Voice"])
app.include_router(routes_evaluation.router, prefix="/evaluation", tags=["Evaluation"])
app.include_router(routes_prescription.router, prefix="/prescription", tags=["Prescription"])