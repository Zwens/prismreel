from typing import List, Optional
from enum import Enum
from pydantic import BaseModel, Field


class PlaygroundMode(str, Enum):
    T2I = "t2i"
    I2I = "i2i"
    T2V = "t2v"
    I2V = "i2v"
    R2V = "r2v"
    V2V = "v2v"


class PlaygroundOutput(BaseModel):
    id: str = Field(..., description="Unique identifier (UUID)")
    media_path: str = Field(..., description="Generated file path relative to output/")
    media_type: str = Field(..., description="Output media type: image or video")
    thumbnail_path: Optional[str] = Field(None, description="Thumbnail file path relative to output/")
    saved_to_library: bool = Field(False, description="Whether this output has been saved to the project library")
    total_tokens: Optional[int] = Field(None, description="Provider-reported token count for this generation, when available")
    cost_usd: Optional[float] = Field(None, description="Estimated cost in USD for this generation, when a price table entry exists")


class PlaygroundGeneration(BaseModel):
    id: str = Field(..., description="Unique identifier (UUID)")
    owner_id: str = Field("", description="User id of the generation's owner; empty for pre-migration/anonymous records")
    mode: PlaygroundMode = Field(..., description="Generation mode")
    model_id: str = Field(..., description="Model identifier from model catalog")
    prompt: str = Field(..., description="Text prompt for generation")
    negative_prompt: Optional[str] = Field(None, description="Negative prompt to exclude undesired elements")
    input_media: List[str] = Field(default_factory=list, description="Input file paths for image/video-conditioned modes")
    parameters: dict = Field(default_factory=dict, description="Generation parameters (resolution, duration, aspect_ratio, etc.)")
    batch_size: int = Field(1, ge=1, le=4, description="Number of outputs to generate per request (1-4)")
    outputs: List[PlaygroundOutput] = Field(default_factory=list, description="Generated outputs")
    status: str = Field("pending", description="Generation status: pending/processing/completed/failed")
    error: Optional[str] = Field(None, description="Error message if generation failed")
    created_at: str = Field(..., description="Creation timestamp in ISO 8601 format")


class PlaygroundTemplate(BaseModel):
    id: str = Field(..., description="Unique identifier (UUID)")
    name: str = Field(..., description="Template display name")
    category: str = Field("general", description="Template category: image/video/general")
    prompt: str = Field(..., description="Template prompt text")
    negative_prompt: Optional[str] = Field(None, description="Default negative prompt")
    default_mode: Optional[PlaygroundMode] = Field(None, description="Default generation mode for this template")
    default_model_id: Optional[str] = Field(None, description="Default model identifier")
    default_parameters: dict = Field(default_factory=dict, description="Default generation parameters")
    created_at: str = Field(..., description="Creation timestamp in ISO 8601 format")
    updated_at: str = Field(..., description="Last update timestamp in ISO 8601 format")


class OfficialDigitalCharacter(BaseModel):
    asset_id: str = Field(..., description="Ark asset id; referenced as asset://<asset_id>")
    group_id: str = Field(..., description="Ark asset group id")
    nationality: str = Field(..., description="Character tag: nationality")
    gender: str = Field(..., description="Character tag: gender")
    age: int = Field(..., description="Character tag: age")
    occupation: str = Field(..., description="Character tag: occupation")
    biography: str = Field(..., description="Character biography shown in ModelArk Playground")


class GenerateRequest(BaseModel):
    mode: PlaygroundMode = Field(..., description="Generation mode")
    model_id: str = Field(..., description="Model identifier from model catalog")
    prompt: str = Field(..., description="Text prompt for generation")
    negative_prompt: Optional[str] = Field(None, description="Negative prompt to exclude undesired elements")
    input_media: Optional[List[str]] = Field(None, description="Input file paths for image/video-conditioned modes")
    parameters: Optional[dict] = Field(None, description="Generation parameters (resolution, duration, aspect_ratio, etc.)")
    batch_size: Optional[int] = Field(1, ge=1, le=4, description="Number of outputs to generate (1-4)")


class SaveToLibraryRequest(BaseModel):
    category: str = Field("general", description="Library category for the saved output")


class EstimateCostRequest(BaseModel):
    mode: PlaygroundMode = Field(..., description="Generation mode")
    model_id: str = Field(..., description="Model identifier from model catalog")
    parameters: Optional[dict] = Field(None, description="Generation parameters (resolution, duration, etc.)")
    batch_size: Optional[int] = Field(1, ge=1, le=4, description="Number of outputs to generate (1-4)")


class EstimateCostResponse(BaseModel):
    cost_usd: Optional[float] = Field(None, description="Estimated total cost in USD for batch_size outputs, or null when no price table entry exists for this model/resolution")
    per_unit_cost_usd: Optional[float] = Field(None, description="Estimated cost in USD for a single output")
    priced: bool = Field(False, description="Whether a price table entry was found; false means the actual cost is unknown until generation completes")


class CreateTemplateRequest(BaseModel):
    name: str = Field(..., description="Template display name")
    category: Optional[str] = Field("general", description="Template category: image/video/general")
    prompt: str = Field(..., description="Template prompt text")
    negative_prompt: Optional[str] = Field(None, description="Default negative prompt")
    default_mode: Optional[PlaygroundMode] = Field(None, description="Default generation mode")
    default_model_id: Optional[str] = Field(None, description="Default model identifier")
    default_parameters: Optional[dict] = Field(None, description="Default generation parameters")


class UpdateTemplateRequest(BaseModel):
    name: Optional[str] = Field(None, description="Template display name")
    category: Optional[str] = Field(None, description="Template category: image/video/general")
    prompt: Optional[str] = Field(None, description="Template prompt text")
    negative_prompt: Optional[str] = Field(None, description="Default negative prompt")
    default_mode: Optional[PlaygroundMode] = Field(None, description="Default generation mode")
    default_model_id: Optional[str] = Field(None, description="Default model identifier")
    default_parameters: Optional[dict] = Field(None, description="Default generation parameters")
