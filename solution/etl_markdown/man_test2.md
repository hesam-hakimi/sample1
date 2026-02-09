# vector_smoke_test_existing_index.py
import os
import time
from datetime import datetime, timezone

from azure.identity import ManagedIdentityCredential
from azure.search.documents import SearchClient
from azure.search.documents.indexes import SearchIndexClient
from azure.search.documents.models import VectorizedQuery


def get_msi_credential() -> ManagedIdentityCredential:
    """
    If you have multiple user-assigned identities, set AZURE_CLIENT_ID.
    Otherwise, system-assigned MI will be used.
    """
    client_id = os.getenv("AZURE_CLIENT_ID")
    if client_id:
        print(f"Auth: Using User-Assigned Managed Identity (client_id={client_id})")
        return ManagedIdentityCredential(client_id=client_id)

    print("Auth: Using System-Assigned Managed Identity")
    return ManagedIdentityCredential()


def pick_key_and_vector_field(index_def):
    # Key field
    key_field = None
    for f in index_def.fields:
        if getattr(f, "key", False):
            key_field = f.name
            break
    if not key_field:
        raise RuntimeError("Could not find key field in index definition.")

    # Vector field(s)
    vector_fields = []
    for f in index_def.fields:
        dims = getattr(f, "vector_search_dimensions", None)
        if dims is not None:
            vector_fields.append((f.name, int(dims)))

    if not vector_fields:
        raise RuntimeError(
            "No vector fields found in this index (no field has vector_search_dimensions). "
            "Vector search can't run unless the index has a vector field."
        )

    # Pick first vector field by default
    vector_field_name, dims = vector_fields[0]
    return key_field, vector_field_name, dims, vector_fields


def main():
    endpoint = os.environ["AZURE_SEARCH_ENDPOINT"]  # e.g. https://xxxx.search.windows.net
    index_name = os.getenv("AZURE_SEARCH_INDEX_NAME", "texttosql")

    cred = get_msi_credential()

    index_client = SearchIndexClient(endpoint=endpoint, credential=cred)
    search_client = SearchClient(endpoint=endpoint, index_name=index_name, credential=cred)

    # 1) Read index definition (no schema changes)
    print(f"Reading index definition: {index_name} ...")
    index_def = index_client.get_index(index_name)

    key_field, vector_field, dims, vector_fields = pick_key_and_vector_field(index_def)

    print(f"Key field: {key_field}")
    print("Vector fields detected:")
    for name, d in vector_fields:
        print(f"  - {name} (dims={d})")

    print(f"Using vector field: {vector_field} (dims={dims})")

    # 2) Create a deterministic test vector
    # Use a sparse-ish vector: [1, 0, 0, ...]
    test_vector = [0.0] * dims
    test_vector[0] = 1.0

    # 3) Upsert ONE test doc (only key + vector field)
    test_id = f"vector-smoke-{datetime.now(timezone.utc).strftime('%Y%m%d%H%M%S')}"
    doc = {key_field: test_id, vector_field: test_vector}

    print(f"Upserting test doc id={test_id} ...")
    upsert_result = search_client.upload_documents([doc])
    if not all(r.succeeded for r in upsert_result):
        raise RuntimeError(f"Upload failed: {upsert_result}")
    print("Upload: OK")

    # Give the service a moment to index
    time.sleep(2)

    # 4) Vector query with the SAME vector (should retrieve our doc)
    print("Running vector query ...")
    vq = VectorizedQuery(vector=test_vector, k_nearest_neighbors=5, fields=vector_field)

    results = list(
        search_client.search(
            search_text="",
            vector_queries=[vq],
            select=[key_field],
            top=5,
        )
    )

    print("\nTop results:")
    for r in results:
        print(f"- {r[key_field]}  score={r.get('@search.score')}")

    if results and results[0][key_field] == test_id:
        print("\n✅ PASS: Vector search returned the inserted test document as rank #1.")
    else:
        print("\n⚠️  PARTIAL: Vector search returned results, but the test doc was not rank #1.")
        print("This can happen with approximate HNSW on some configs, or if filtering/scoring differs.")
        print("If you want, I can give you a variant that retries or uses a more distinctive vector.")

    # 5) Cleanup: delete the test doc
    print(f"\nDeleting test doc id={test_id} ...")
    del_result = search_client.delete_documents([{key_field: test_id}])
    if not all(r.succeeded for r in del_result):
        print(f"⚠️  Cleanup warning: delete may have failed: {del_result}")
    else:
        print("Cleanup: OK")


if __name__ == "__main__":
    main()
