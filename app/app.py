from fastapi import FastAPI, UploadFile, File, HTTPException
from fastapi.middleware.cors import CORSMiddleware
import ollama
import chromadb
import PyPDF2
import io
import uuid
from chromadb.utils.embedding_functions.ollama_embedding_function import (
    OllamaEmbeddingFunction
)
from app.schema import DocumentSubmission
import os


app = FastAPI(title="RAG App with Chroma DB")

# Allow requests from the frontend container and local dev
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:3000",   # Docker frontend
        "http://localhost:5500",   # VS Code Live Server
        "http://127.0.0.1:5500",
        "http://localhost:8080",
        "*",                       # Remove in production
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Save data to disk so it survives restarts
client = chromadb.PersistentClient(path="./chroma_db")

# Initialize Ollama client for chat
ollama_host = os.getenv("OLLAMA_HOST", "http://localhost:11434")
ollama_client = ollama.Client(host=ollama_host)

# Connect to Ollama's embedding model to convert text into vectors
ef = OllamaEmbeddingFunction(
    model_name="nomic-embed-text",
    url=ollama_host
)


# Create (or reuse) a collection - like a table in a database
collection = client.get_or_create_collection(
    name="personal_profile",
    embedding_function=ef,  # Tells ChromaDB how to convert text to vectors
)


@app.get("/ask")
def ask(question: str, user: str = None):

    # Normalize username to lowercase for consistent matching
    if user:
        user = user.strip().lower()

    # If a user filter is provided, verify the user exists in the collection
    if user:
        user_check = collection.get(where={"username": user})
        if not user_check["ids"]:
            raise HTTPException(
                status_code=404,
                detail=f"User '{user}' not found. No documents have been indexed for this user."
            )

    # Prepare the query parameters
    query_args = {
        "query_texts": [question],
        "n_results": 2
    }

    # Add filter if user is provided
    if user:
        query_args["where"] = {"username": user}

    # Execute the query once
    result = collection.query(**query_args)

    # Safe access to matched chunks (guards against empty collection)
    context_chunks = result["documents"][0] if result["documents"] else []

    # Combine the matching chunks into a single string
    if not context_chunks:
        context = "No relevant context found."
    else:
        context = "\n\n".join(context_chunks)

    # Step 2: AUGMENT - build a prompt that includes the retrieved context
    augmented_prompt = (
        f"Use the following context to answer the question.\n"
        f"If the context doesn't contain relevant information, say so.\n\n"
        f"Context:\n{context}\n\n"
        f"Question: {question}"
    )

    # Step 3: send the augmented question to local LLM
    response = ollama_client.chat(
        model="llama3.2:1b",
        messages=[{"role": "user", "content": augmented_prompt}]
    )

    return {
        "question": question,
        "answer": response.message.content,
        "context_used": context_chunks,
        "filtered_by_user": user,
        "model_used": response.model
    }


#Endpoint to upload text file
@app.post("/upload-pdf")
async def upload_pdf(username : str, file: UploadFile = File(...)):
    # Normalize username to lowercase for consistent matching
    username = username.strip().lower()

    # Read PDF
    pdf_content = await file.read()
    pdf_reader = PyPDF2.PdfReader(io.BytesIO(pdf_content))
    
    text = ""
    for page in pdf_reader.pages:
        extracted = page.extract_text()
        if extracted:
            text += extracted + "\n"
    
    if not text.strip():
        return {"error": "No text found in PDF"}

    # Simple chunking (500 chars)
    chunks = [text[i:i+500] for i in range(0, len(text), 500)]
    
    # Add to ChromaDB
    collection.add(
        ids = [f"{username} - chunk{i}" for i in range(len(chunks))],
        documents = chunks,
        metadatas = [
            {"source" : "profile", "username" : username, "chunk_idx": i}
            for i in range(len(chunks))
        ])
    
    return {
        "message": f"Added {len(chunks)} chunks for user '{username}'",
        "username": username,
        "chunks_added": len(chunks)
    }


#Post endpoint for User data Ingestion
@app.post("/user_documents")
def add_user_document(submission: DocumentSubmission):
    # Normalize username to lowercase for consistent matching
    username = submission.username.strip().lower()

    chunks = [chunk.strip() for chunk in submission.content.split("\n\n") if chunk.split()]

    #Store chunks in the database
    collection.add(
        ids=[f"{username} - chunk{i}" for i in range(len(chunks))],
        documents= chunks,
        metadatas= [
            {"source" : "profile", "username" : username, "chunk_idx": i}
            for i in range(len(chunks))
        ]
    )

    return {
        "message": f"Added {len(chunks)} chunks for user '{username}'",
        "username": username,
        "chunks_added": len(chunks)
    }

#Delete user Database
@app.delete("/user_documents/{username}")
def delete_user_documents(username : str):
    # Normalize username to lowercase for consistent matching
    username = username.strip().lower()

    # Check if user has any documents before deleting
    user_docs = collection.get(where={"username": username})
    if user_docs["ids"]:
        collection.delete(where={"username": username})
        return {
            "message": f"Deleted all documents for user '{username}'",
            "username": username,
            "chunks_deleted": "all"
        }
    else:
        raise HTTPException(
            status_code=404,
            detail=f"No documents found for user '{username}'"
        )

