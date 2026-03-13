import os
from fastapi import APIRouter, HTTPException, Depends
from langchain_anthropic import ChatAnthropic
from langchain_core.messages import HumanMessage
from src.utils.github_client import GitHubClient
from src.api.utils.postgres_manager import get_db

router = APIRouter()


def get_markdown_files(root_dir: str):
    """Recursively find all markdown files in the cloned repository."""
    md_files = []
    for root, _, files in os.walk(root_dir):
        for file in files:
            if file.endswith(".md"):
                # Store the relative path for cleaner processing
                full_path = os.path.join(root, file)
                md_files.append(full_path)
    return md_files


@router.post("/sync-tenant/{name_in_url}")
async def sync_tenant(name_in_url: str, db=Depends(get_db)):
    # Match your specific column names: tenant_name and github_url
    query = "SELECT tenant_id, github_url FROM tenants WHERE tenant_name = %s"
    tenant = db.execute(query, (name_in_url,)).fetchone()

    if not tenant:
        raise HTTPException(
            status_code=404, detail=f"Tenant '{name_in_url}' not found."
        )

    github_url = tenant[0]

    try:
        # 2. Trigger the GitHubClient to pull the repo
        # Ensure your GitHubClient.clone_repo returns the local path where it was cloned
        client = GitHubClient()
        repo_path = client.clone_repo(github_url)

        # 3. Recursively find all marketing content
        md_files = get_markdown_files(repo_path)

        if not md_files:
            return {
                "status": "success",
                "message": "Repo synced, but no markdown files found.",
            }

        # 4. Initialize the AI Brain (Claude 3.5 Sonnet)
        llm = ChatAnthropic(model="claude-3-5-sonnet-20241022", temperature=0)

        # Simple test prompt to verify Claude can see your file structure
        file_list_str = "\n".join(
            [os.path.basename(f) for f in md_files[:10]]
        )  # First 10 for brevity
        prompt = f"I have synced the following marketing files: \n{file_list_str}\n\nBased on these filenames, what is the primary focus of this marketing codebase?"

        response = llm.invoke([HumanMessage(content=prompt)])

        return {
            "status": "sync_complete",
            "tenant": tenant_name,
            "files_discovered": len(md_files),
            "initial_analysis": response.content,
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Sync failed: {str(e)}")
