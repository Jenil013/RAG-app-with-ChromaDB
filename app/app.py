from fastapi import FastAPI, UploadFile, File
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

# Save data to disk so it survives restarts
client = chromadb.PersistentClient(path="./chroma_db")

# Initialize Ollama client for chat
ollama_host = os.getenv("OLLAMA_HOST", "http://host.docker.internal:11434")
ollama_client = ollama.Client(host=ollama_host)

  # Connect to Ollama's embedding model to convert text into vectors
ef = OllamaEmbeddingFunction(
    model_name="nomic-embed-text",
    url=ollama_host,  # Ollama's address (service name in docker-compose)
)


# Create (or reuse) a collection - like a table in a database
collection = client.get_or_create_collection(
    name="personal_profile",
    embedding_function=ef,  # Tells ChromaDB how to convert text to vectors
)


@app.get("/ask")
def ask(question: str, user: str = None):

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

    # Simple chunking (1000 chars)
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

    chunks = [chunk.strip() for chunk in submission.content.split("\n\n") if chunk.split()]

    #Store chunks in the database
    collection.add(
        ids=[f"{submission.username} - chunk{i}" for i in range(len(chunks))],
        documents= chunks,
        metadatas= [
            {"source" : "profile", "username" : submission.username, "chunk_idx": i}
            for i in range(len(chunks))
        ]
    )

    return {
        "message": f"Added {len(chunks)} chunks for user '{submission.username}'",
        "username": submission.username,
        "chunks_added": len(chunks)
    }