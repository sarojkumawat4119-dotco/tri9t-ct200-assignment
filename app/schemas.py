from pydantic import BaseModel, Field
from typing import Literal
class IngestRequest(BaseModel): pdf_path: str
class SelectionRequest(BaseModel): name: str = Field(min_length=1,max_length=200); node_ids: list[int] = Field(min_length=1)
class GenerateRequest(BaseModel): selection_id: int
class TestCase(BaseModel): title: str; objective: str; preconditions: list[str] = []; steps: list[str] = Field(min_length=1); expected_result: str; severity: Literal['critical','high','medium','low'] = 'medium'; source_node_ids: list[int] = []
class GenerationPayload(BaseModel): test_cases: list[TestCase] = Field(min_length=3,max_length=5)
