# azure_ai_search_vector_smoke_test_msi.py
import os
import time
from typing import List

from azure.identity import ManagedIdentityCredential
from azure.search.documents import SearchClient
from azure.search.documents.indexes import SearchIndexClient
from azure.search.documents.indexes.models import (
    SearchIndex,
    SimpleField,
    SearchField,
    SearchFieldDataType,
    VectorSearch,
    HnswAlgorithmConfiguration,
    VectorSearchProfile,
)
from azure.search.documents.models import VectorizedQuery


def get_msi_credential() -> ManagedIdentityCredential:
    """
    If AZURE_CLIENT_ID is set, we assume User-Assigned MI and pass client_id.
    Otherwise we use System-Assigned MI.
    """
    client_id = os.getenv("AZURE_CLIENT_ID")
    if client_id:
        print(f"Auth: Using User-Assigned Managed Identity (client_id={client_id})")
        return ManagedIdentityCredential(client_id=client_id)

    print("Auth: Using System-Assigned Managed Identity")
    return ManagedIdentityCredential()


def create_or_update_vector_index(index_client: SearchIndexClient, index_name: str, dims: int) -> None:
    """
    Uses the newer "algorithms + profiles" model.
    The vector field references vector_search_profile_name (not the algorithm name).
    """
    vector_search = VectorSearch(
        algorithms=[HnswAlgorithmConfiguration(name="hnsw-config")],
        profiles=[VectorSearchProfile(name="hnsw-profile", algorithm_configuration_name="hnsw-config")],
    )

    fields = [
        SimpleField(name="id", type=SearchFieldDataType.String, key=True),
        SearchField(name="content", type=SearchFieldDataType.String, searchable=True, retrievable=True),

        SearchField(
            name="contentVector",
            type=SearchFieldDataType.Collection(SearchFieldDataType.Single),
            searchable=True,
            retrievable=True,
            vector_search_dimensions=dims,
            vector_search_profile_name="hnsw-profile",
        ),
    ]

    index = SearchIndex(name=index_name, fields=fields, vector_search=vector_search)

    print(f"Index: create_or_update_index('{index_name}') ...")
    index_client.create_or_update_index(index)
    print("Index: OK")


def upload_sample_docs(search_client: SearchClient) -> None:
    # Simple vectors for a sanity check
    docs = [
        {"id": "1", "content": "red apple",   "contentVector": [1.0, 0.0, 0.0, 0.0]},
        {"id": "2", "content": "green apple", "contentVector": [0.9, 0.1, 0.0, 0.0]},
        {"id": "3", "content": "blue sky",    "contentVector": [0.0, 0.0, 1.0, 0.0]},
        {"id": "4", "content": "night stars", "contentVector": [0.0, 0.0, 0.9, 0.1]},
        {"id": "5", "content": "car engine",  "contentVector": [0.0, 1.0, 0.0, 0.0]},
    ]

    print("Docs: upload_documents ...")
    results = search_client.upload_documents(docs)
    failed = [r for r in results if not r.succeeded]
    if failed:
        raise RuntimeError(f"Upload failed: {failed}")
    print("Docs: OK")


def run_vector_query(search_client: SearchClient, k: int = 3) -> None:
    # Vector close to “apple”
    q = VectorizedQuery(
        vector=[1.0, 0.0, 0.0, 0.0],
        k_nearest_neighbors=k,
        fields="contentVector",
    )

    print("Query: vector search ...")
    results = search_client.search(
        search_text="",               # empty for pure vector
        vector_queries=[q],
        select=["id", "content"],
        top=k,
    )

    print("\nTop matches:")
    for r in results:
        print(f"- id={r['id']} content={r['content']} score={r['@search.score']}")


def main() -> None:
    endpoint = os.environ["AZURE_SEARCH_ENDPOINT"]  # e.g. https://xxxx.search.windows.net
    index_name = os.getenv("AZURE_SEARCH_INDEX_NAME", "vector-smoke-test")
    dims = int(os.getenv("AZURE_VECTOR_DIMS", "4"))

    credential = get_msi_credential()

    index_client = SearchIndexClient(endpoint=endpoint, credential=credential)
    search_client = SearchClient(endpoint=endpoint, index_name=index_name, credential=credential)

    # 1) Create/update index
    try:
        create_or_update_vector_index(index_client, index_name=index_name, dims=dims)
    except Exception as e:
        print("\nFAILED creating/updating index.")
        print("Common causes:")
        print("- Index quota exceeded (you hit max indexes). Reuse an existing index name or delete one.")
        print("- RBAC missing: identity lacks Search Service Contributor.")
        raise

    # 2) Upload docs
    try:
        upload_sample_docs(search_client)
    except Exception as e:
        print("\nFAILED uploading documents.")
        print("Common causes:")
        print("- RBAC missing: identity lacks Search Index Data Contributor.")
        raise

    # 3) Wait briefly for indexing
    time.sleep(2)

    # 4) Query
    run_vector_query(search_client)


if __name__ == "__main__":
    main()
