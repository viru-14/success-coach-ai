from chromadb.utils.embedding_functions import OpenAIEmbeddingFunction
import chromadb
import streamlit as st
from dotenv import load_dotenv
from pathlib import Path
import os

load_dotenv()

BASE_DIR = Path(__file__).parent.parent

try:
    api_key = st.secrets["OPENAI_API_KEY"]
except Exception:
    api_key = os.getenv("OPENAI_API_KEY")

embedding_fn = OpenAIEmbeddingFunction(
    api_key=api_key,
    model_name="text-embedding-3-small"
)

chroma_client = chromadb.PersistentClient(path=str(BASE_DIR / "RAG" / "chromaDB"))
collection = chroma_client.get_or_create_collection(
    name="product_features",
    embedding_function=embedding_fn
)


def get_setup_data(query: str) -> str:
    results = collection.query(
        query_texts=[query],
        n_results=3
    )

    chunks = results["documents"][0]

    if not chunks:
        return "No relevant platform data found for this query."

    formatted = [f"[Chunk {i}]\n{chunk}" for i, chunk in enumerate(chunks, 1)]
    return "\n\n".join(formatted)