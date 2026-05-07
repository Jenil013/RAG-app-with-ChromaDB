from pydantic import BaseModel

class DocumentSubmission(BaseModel):
    username: str
    content: str

