
from pydantic import BaseModel, Field
from typing import Optional


class TripRequest(BaseModel):
    tpep_pickup_datetime: str
    PULocationID: int = Field(..., ge=1, le=265)
    DOLocationID: int = Field(..., ge=1, le=265)
    passenger_count: int = Field(default=1, ge=1, le=6)
    VendorID: int = Field(default=1, ge=1, le=2)
    RatecodeID: int = Field(default=1, ge=1, le=6)
    trip_distance: float = Field(..., gt=0)
    payment_type: int = Field(default=1, ge=1, le=6)

    model_config = {
        "json_schema_extra": {
            "example": {
                "tpep_pickup_datetime": "2019-01-15T14:30:00",
                "PULocationID": 161,
                "DOLocationID": 237,
                "passenger_count": 1,
                "VendorID": 1,
                "RatecodeID": 1,
                "trip_distance": 2.5,
                "payment_type": 1,
            }
        }
    }


class PredictionResponse(BaseModel):
    predicted_duration_minutes: float
    model_version: str
    model_alias: str
    prediction_time_ms: Optional[float] = Field(
        None,
        description="Time taken to compute the prediction in milliseconds"
    )
