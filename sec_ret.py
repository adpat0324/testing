kubectl -n <NAMESPACE> exec $pod -- python - <<'PY'
import os, json, time, urllib.request

# Use existing env vars inside pod
aoai_endpoint = os.environ["AZURE_OPENAI_ENDPOINT"].rstrip("/")
aoai_key = os.environ["AZURE_OPENAI_API_KEY"]
deploy = os.environ.get("AZURE_OPENAI_EMBEDDINGS_DEPLOYMENT","ged_us_gpt_text_embedding_large")
aoai_ver = os.environ.get("AZURE_OPENAI_API_VERSION","2024-02-01")

search_endpoint = os.environ["AZURE_SEARCH_ENDPOINT"].rstrip("/")
search_key = os.environ["AZURE_SEARCH_API_KEY"]
index = os.environ["AZURE_SEARCH_INDEX"]
vector_field = os.environ.get("AZURE_SEARCH_VECTOR_FIELD","contentVector")
api_ver = os.environ.get("AZURE_SEARCH_API_VERSION","2024-07-01")

def post(url, headers, payload):
    req = urllib.request.Request(url, data=json.dumps(payload).encode(), headers=headers, method="POST")
    with urllib.request.urlopen(req, timeout=60) as r:
        return json.loads(r.read().decode())

# 1) Embed
emb = post(
    f"{aoai_endpoint}/openai/deployments/{deploy}/embeddings?api-version={aoai_ver}",
    {"Content-Type":"application/json","api-key": aoai_key},
    {"input":"aks-smoke-test"}
)
vec = emb["data"][0]["embedding"]

# 2) Upsert doc with vector
doc_id = f"smoke-{int(time.time())}"
post(
    f"{search_endpoint}/indexes/{index}/docs/index?api-version={api_ver}",
    {"Content-Type":"application/json","api-key": search_key},
    {"value":[{"@search.action":"mergeOrUpload","id":doc_id,"smokeText":"aks-smoke-test",vector_field:vec}]}
)

# 3) Read back doc (vector may be non-retrievable)
got = urllib.request.urlopen(
    urllib.request.Request(
        f"{search_endpoint}/indexes/{index}/docs('{doc_id}')?api-version={api_ver}",
        headers={"api-key": search_key},
        method="GET"
    ), timeout=60
).read().decode()

print("PASS: wrote doc", doc_id)
print("NOTE: vector may not be returned if non-retrievable")
PY
