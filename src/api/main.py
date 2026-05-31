import os
from typing import List, Optional

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from src.models.preferences import Budget, UserPreferences
from src.services.orchestrator import get_recommendations
from src.services.validation import ValidationError
from src.data.repository import get_repository

app = FastAPI(title="Zomato AI Recommender API")

class PreferencesRequest(BaseModel):
    location: str
    budget: str
    cuisine: Optional[str] = None
    min_rating: float = 3.5
    additional_preferences: Optional[str] = None

@app.get("/api/locations")
async def get_locations():
    repo = get_repository()
    return {"locations": repo.unique_locations()}

@app.post("/api/recommend")
async def recommend(req: PreferencesRequest):
    try:
        additional = [tag.strip() for tag in req.additional_preferences.split(",")] if req.additional_preferences else []
        prefs = UserPreferences(
            location=req.location,
            budget=Budget.from_str(req.budget),
            cuisine=req.cuisine if req.cuisine and req.cuisine.lower() != "any" else None,
            min_rating=req.min_rating,
            additional_preferences=additional
        )
        response = get_recommendations(prefs)
        
        # We need to serialize the response properly for FastAPI/Pydantic
        # RecommendationResponse is a dataclass
        return response
    except ValidationError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

static_dir = os.path.join(os.path.dirname(__file__), "../ui/static")
app.mount("/static", StaticFiles(directory=static_dir), name="static")

@app.get("/")
async def root():
    return FileResponse(os.path.join(static_dir, "index.html"))
