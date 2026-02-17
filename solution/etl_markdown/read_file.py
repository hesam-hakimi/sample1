from azure.core.exceptions import ResourceNotFoundError, HttpResponseError
from azure.search.documents.indexes.models import (
    SearchIndex,
    SimpleField,
    SearchField,
    SearchFieldDataType,
    VectorSearch,
    HnswAlgorithmConfiguration,
    VectorSearchProfile,
)

def _has_field(index: SearchIndex, name: str) -> bool:
    return any(f.name == name for f in (index.fields or []))

def _get_field(index: SearchIndex, name: str):
    for f in (index.fields or []):
        if f.name == name:
            return f
    return None

def _ensure_vector_config(index: SearchIndex):
    # Ensure vector_search exists and has our algo/profile
    if index.vector_search is None:
        index.vector_search = VectorSearch(
            algorithms=[HnswAlgorithmConfiguration(name="hnsw")],
            profiles=[VectorSearchProfile(name="vector-profile", algorithm_configuration_name="hnsw")],
        )
        return

    # Add algorithm if missing
    algos = index.vector_search.algorithms or []
    if not any(a.name == "hnsw" for a in algos):
        algos.append(HnswAlgorithmConfiguration(name="hnsw"))
    index.vector_search.algorithms = algos

    # Add profile if missing
    profiles = index.vector_search.profiles or []
    if not any(p.name == "vector-profile" for p in profiles):
        profiles.append(VectorSearchProfile(name="vector-profile", algorithm_configuration_name="hnsw"))
    index.vector_search.profiles = profiles

def ensure_index_vector_enabled(index_client, index_name: str, vector_dim: int) -> str:
    """
    - If index doesn't exist: create it fresh (vector-enabled).
    - If index exists: ONLY add missing fields/config (no changes to existing fields).
    - If upgrade is not possible: create a new index name automatically.
    Returns the index name that should be used.
    """
    try:
        idx = index_client.get_index(index_name)

        # 1) Ensure keyword field exists (add only if missing)
        if not _has_field(idx, "content"):
            idx.fields.append(
                SearchField(name="content", type=SearchFieldDataType.String, searchable=True)
            )

        # 2) Ensure vector field exists (add only if missing)
        if _has_field(idx, "content_vector"):
            # If it exists, make sure dimensions match. If not, cannot change -> new index needed.
            f = _get_field(idx, "content_vector")
            existing_dim = getattr(f, "vector_search_dimensions", None)
            if existing_dim is not None and int(existing_dim) != int(vector_dim):
                raise HttpResponseError(
                    message=f"content_vector exists with dimensions={existing_dim}, cannot change to {vector_dim}"
                )
        else:
            idx.fields.append(
                SearchField(
                    name="content_vector",
                    type=SearchFieldDataType.Collection(SearchFieldDataType.Single),
                    searchable=True,
                    vector_search_dimensions=vector_dim,
                    vector_search_profile_name="vector-profile",
                )
            )

        # 3) Ensure vector search config exists
        _ensure_vector_config(idx)

        # 4) Update index WITHOUT redefining existing fields like 'id'
        index_client.create_or_update_index(idx)
        print(f"[OK] Upgraded index in place: {index_name}")
        return index_name

    except ResourceNotFoundError:
        # Create fresh index
        fields = [
            SimpleField(name="id", type=SearchFieldDataType.String, key=True, filterable=True),

            SearchField(name="content", type=SearchFieldDataType.String, searchable=True),

            SearchField(
                name="content_vector",
                type=SearchFieldDataType.Collection(SearchFieldDataType.Single),
                searchable=True,
                vector_search_dimensions=vector_dim,
                vector_search_profile_name="vector-profile",
            ),

            # You can add more fields here if you want on a NEW index.
            # (But do not try to "change" existing ones on an old index.)
        ]

        vector_search = VectorSearch(
            algorithms=[HnswAlgorithmConfiguration(name="hnsw")],
            profiles=[VectorSearchProfile(name="vector-profile", algorithm_configuration_name="hnsw")],
        )

        new_index = SearchIndex(name=index_name, fields=fields, vector_search=vector_search)
        index_client.create_or_update_index(new_index)
        print(f"[OK] Created new index: {index_name}")
        return index_name

    except HttpResponseError as e:
        msg = str(e)
        # If upgrade fails (immutable fields), create a new versioned index
        if "cannot be changed" in msg.lower() or "OperationNotAllowed" in msg:
            fallback = f"{index_name}_v2"
            print(f"[WARN] Cannot upgrade '{index_name}'. Creating '{fallback}' instead.")

            fields = [
                SimpleField(name="id", type=SearchFieldDataType.String, key=True, filterable=True),
                SearchField(name="content", type=SearchFieldDataType.String, searchable=True),
                SearchField(
                    name="content_vector",
                    type=SearchFieldDataType.Collection(SearchFieldDataType.Single),
                    searchable=True,
                    vector_search_dimensions=vector_dim,
                    vector_search_profile_name="vector-profile",
                ),
            ]

            vector_search = VectorSearch(
                algorithms=[HnswAlgorithmConfiguration(name="hnsw")],
                profiles=[VectorSearchProfile(name="vector-profile", algorithm_configuration_name="hnsw")],
            )

            new_index = SearchIndex(name=fallback, fields=fields, vector_search=vector_search)
            index_client.create_or_update_index(new_index)
            return fallback

        raise
