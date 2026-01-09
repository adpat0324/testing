from azure.search.documents import SearchClient
from azure.identity import DefaultAzureCredential

endpoint = "https://<your-search-service-name>.search.windows.net"
index_name = "ib-eq-parser-embd-index"

credential = DefaultAzureCredential()

client = SearchClient(
    endpoint=endpoint,
    index_name=index_name,
    credential=credential
)

# --- READ TEST: pull 5 docs ---
results = client.search(
    search_text="*",
    top=5,
    select=["id", "workflow_id", "chat"]
)

print("Top documents:")
for doc in results:
    print("------------------------------------------------")
    print("id:", doc.get("id"))
    print("workflow_id:", doc.get("workflow_id"))
    print("chat:", doc.get("chat")[:200])
