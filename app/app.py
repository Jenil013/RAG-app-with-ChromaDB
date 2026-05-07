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

app = FastAPI(title="RAG App with Chroma DB")

# Save data to disk so it survives restarts
client = chromadb.PersistentClient(path="./chroma_db")

# Connect to Ollama's embedding model to convert text into vectors
ef = OllamaEmbeddingFunction(
    model_name="nomic-embed-text",
    url="http://localhost:11434",  # Ollama's default local address
)

# Create (or reuse) a collection - like a table in a database
collection = client.get_or_create_collection(
    name="personal_profile",
    embedding_function=ef,  # Tells ChromaDB how to convert text to vectors
)


@app.get("/ask")
def ask(question: str, user: str = None):
    
    query_params = collection.query(
        query_texts=[question], #Chroma db converts this in vector
        n_results = 2
    )

    if user:
        query_params["where"] = {"username": user}


    result = collection.query(**query_params)
    # Combine the matching chunks into a single string
    context = "\n\n".join(result["documents"][0])

    # Step 2: AUGMENT - build a prompt that includes the retrieved context
    augmented_prompt = f"""Use the following context to answer the question.
        If the context doesn't contain relevant information, say so.

        Context:
        {context}

        Question: {question}"""

    #Step3: send the augmented question to local LLM
    response = ollama.chat(
        model="gpt-oss:120b-cloud",
        messages=[{"role":"user", "content":augmented_prompt}]
    )

    return {
        "question": question,
        "answer": response["message"]["content"],
        "context_used": result["documents"][0],
        "filtered_by_user": user
    }

#Endpoint to upload text file
@app.post("/upload-pdf")
async def upload_pdf(file: UploadFile = File(...)):
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
    chunks = [text[i:i+1000] for i in range(0, len(text), 1000)]
    ids = [f"{file.filename}_{uuid.uuid4()}" for _ in chunks]
    
    # Add to ChromaDB
    collection.add(documents=chunks, ids=ids)
    
    return {"message": f"Added {len(chunks)} chunks from {file.filename}"}


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