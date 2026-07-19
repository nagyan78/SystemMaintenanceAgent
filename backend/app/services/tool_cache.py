import hashlib, json
from backend.app.config import Settings
from backend.app.repositories.version_repo import VersionRepository

def normalized_args_hash(args):
    return hashlib.sha256(json.dumps(args, ensure_ascii=False, sort_keys=True, default=str).encode()).hexdigest()

class DataRevisionResolver:
    TAXONOMY_TOOLS={"get_node_detail","get_node_path","get_children","get_siblings"}
    def __init__(self, settings: Settings): self.settings=settings
    def for_tool(self, tool_name, args):
        if tool_name in self.TAXONOMY_TOOLS: return f"taxonomy:{int(args['version_id'])}"
        if tool_name == "search_similar_nodes":
            version_id=int(args["version_id"]); version=VersionRepository(self.settings).get_version(version_id)
            if not version: raise ValueError("version not found")
            return f"qdrant:{self.settings.qdrant_collection}:{version_id}:{self.settings.embedding_model}:{version.get('vector_index_generation',0)}"
        if "run_id" in args: return f"agent_run:{args['run_id']}"
        raise ValueError(f"No data revision strategy for tool {tool_name}")
