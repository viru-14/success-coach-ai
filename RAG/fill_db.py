from langchain_community.document_loaders import TextLoader
from langchain_text_splitters import RecursiveCharacterTextSplitter
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


def build_db():
    """
    Load data.md, split into chunks, embed with OpenAI, and upsert into ChromaDB.
    Run this once (or whenever data.md is updated) before starting the app.
    """
    embedding_fn = OpenAIEmbeddingFunction(
        api_key=api_key,
        model_name="text-embedding-3-small"
    )

    chroma_client = chromadb.PersistentClient(path=str(BASE_DIR / "RAG" / "chromaDB"))
    collection = chroma_client.get_or_create_collection(
        name="product_features",
        embedding_function=embedding_fn
    )

    loader = TextLoader(str(BASE_DIR / "RAG" / "data.md"), encoding="utf-8")
    raw_documents = loader.load()

    text_splitter = RecursiveCharacterTextSplitter(
        chunk_size=300,
        chunk_overlap=100,
        length_function=len,
        is_separator_regex=False,
    )
    chunks = text_splitter.split_documents(raw_documents)

    documents = []
    ids = []
    metadata = []

    for i, chunk in enumerate(chunks):
        documents.append(chunk.page_content)
        metadata.append(chunk.metadata)
        ids.append(f"ID {i}")

    collection.upsert(
        documents=documents,
        metadatas=metadata,
        ids=ids,
    )

    print(f"Done — {len(chunks)} chunks upserted with OpenAI embeddings.")


if __name__ == "__main__":
    build_db()