import chromadb
from chromadb.utils.embedding_functions.ollama_embedding_function import (
    OllamaEmbeddingFunction,
)

#Read the profile file
with open("profile.txt", "r") as file:
    text = file.read()

#Chunks from the text
chunks = [chunk.strip() for chunk in text.split("\n\n") if chunk.strip()]

print(f"Successfully loaded {len(chunks)} from the profile.txt")

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

#Add chunks from our file to collections
collection.add(
    ids=[f"chunk{i}" for  i in range(len(chunks))],
    documents=chunks,
    metadatas=[{"source": "profile", "chunk_index": i} for i in range(len(chunks))]
)

print(f"Added {len(chunks)} chunks to the personal profile collecion in our Chroma DB")
print("Knowledge base build successful")