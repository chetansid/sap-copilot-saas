
import os
import glob
from langchain_postgres import PGVector
from langchain_openai import OpenAIEmbeddings
from langchain_community.document_loaders import PyPDFLoader
from langchain_text_splitters import RecursiveCharacterTextSplitter
from dotenv import load_dotenv

load_dotenv()

CHROMA_DIR = "chroma_db"

def _conn():
    url = os.environ["DATABASE_URL"].replace("postgres://", "postgresql://", 1)
    return url.replace("postgresql://", "postgresql+psycopg://", 1)  # psycopg3 driver

# def ingest_file(file_path: str, doc_type: str) -> int:
#     loader = PyPDFLoader(file_path)
#     documents = loader.load()

#     # Tag each chunk with document type and source
#     for doc in documents:
#         doc.metadata["doc_type"] = doc_type
#         doc.metadata["source_file"] = os.path.basename(file_path)

#     splitter = RecursiveCharacterTextSplitter(
#         chunk_size=500,
#         chunk_overlap=50
#     )
#     chunks = splitter.split_documents(documents)

#     embeddings = OpenAIEmbeddings()
#     vectorstore = Chroma(
#         persist_directory=CHROMA_DIR,
#         embedding_function=embeddings
#     )
#     vectorstore.add_documents(chunks)

#     return len(chunks)


# def get_vectorstore():
#     embeddings = OpenAIEmbeddings()
#     return Chroma(
#         persist_directory=CHROMA_DIR,
#         embedding_function=embeddings
#     )


# def list_ingested_files() -> list:
#     vectorstore = get_vectorstore()
#     collection = vectorstore._collection
#     results = collection.get(include=["metadatas"])
#     files = {}
#     for meta in results["metadatas"]:
#         fname = meta.get("source_file", "unknown")
#         dtype = meta.get("doc_type", "unknown")
#         files[fname] = dtype
#     return [{"file": k, "type": v} for k, v in files.items()]



# def get_vectorstore_for_user(user_id: int, project_id: int):
#     """Get user-scoped vectorstore."""
#     embeddings = OpenAIEmbeddings()
#     return Chroma(
#         persist_directory=f"chroma_db/user_{user_id}/project_{project_id}",
#         embedding_function=embeddings
#     )
def get_vectorstore_for_user(user_id: int, project_id: int):
    return PGVector(
        embeddings=OpenAIEmbeddings(),
        collection_name=f"u{user_id}_p{project_id}",   # one collection per tenant+project
        connection=_conn(),
        use_jsonb=True,
    )

def ingest_file_for_user(file_path, doc_type, user_id, project_id) -> int:
    docs = PyPDFLoader(file_path).load()
    for d in docs:
        d.metadata.update(doc_type=doc_type, source_file=os.path.basename(file_path))
    chunks = RecursiveCharacterTextSplitter(chunk_size=500, chunk_overlap=50).split_documents(docs)
    get_vectorstore_for_user(user_id, project_id).add_documents(chunks)
    return len(chunks)

def delete_project_vectors(user_id: int, project_id: int):
    get_vectorstore_for_user(user_id, project_id).delete_collection()