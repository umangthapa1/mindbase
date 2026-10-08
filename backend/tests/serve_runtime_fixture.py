"""Serve source in a disposable workspace for the real-browser runtime test.

No live data, credentials, model downloads, or mailbox connections are used.
The same fixture directory can be reused to exercise a full server restart.
"""
import argparse
import os
from pathlib import Path
import re
import shutil
import sys


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--workspace", required=True)
    parser.add_argument("--port", required=True, type=int)
    args = parser.parse_args()
    workspace = Path(args.workspace).resolve()
    if not workspace.is_relative_to(Path("/tmp/omnirush")) or workspace == Path("/tmp/omnirush"):
        parser.error("Fixture workspace must be a child of /tmp/omnirush")
    root = Path(__file__).resolve().parents[2]
    for name in ("backend", "frontend"):
        shutil.copytree(root / name, workspace / name, dirs_exist_ok=True,
                        ignore=shutil.ignore_patterns(".env*", "__pycache__", ".pytest_cache", "*.db", "*.log"))
    # Exercise the actual app scripts; replace only external markdown/highlight assets.
    index = workspace / "frontend" / "index.html"
    html = re.sub(r'<script\b[^>]*src="https://[^>]*></script>', "", index.read_text())
    html = re.sub(r'<link\b[^>]*href="https://[^>]*>', "", html)
    stubs = """<script>
        window.marked = {setOptions(){}, Renderer: class {}, parse(text) {
            const el = document.createElement('span'); el.textContent = text; return el.innerHTML;
        }};
        window.hljs = {highlightElement(){}, highlightAuto(text){return {value:text};}};
    </script>"""
    index.write_text(html.replace("</head>", stubs + "</head>"))
    css = workspace / "frontend" / "css" / "globals.css"
    css.write_text(re.sub(r"^@import.*$", "", css.read_text(), flags=re.M))
    os.environ.update(EMAIL_AUTO_SYNC="false", PYTHON_DOTENV_DISABLED="1", ANONYMIZED_TELEMETRY="False",
                      OLLAMA_HOST="http://127.0.0.1:9", HOME=str(workspace))
    os.chdir(workspace)
    sys.path.insert(0, str(workspace / "backend"))
    from ollama import ollama_client

    async def offline(*args, **kwargs):
        return False

    async def no_models(*args, **kwargs):
        return []

    async def embedding(*args, **kwargs):
        return [0.1, 0.2, 0.3, 0.4]

    async def unexpected_model(*args, **kwargs):
        raise RuntimeError("A deterministic reminder must not call a model")

    ollama_client.check_health = offline
    ollama_client.list_models = no_models
    ollama_client.get_model = unexpected_model
    ollama_client.generate_embedding = embedding
    import uvicorn
    from main import app
    uvicorn.run(app, host="127.0.0.1", port=args.port, log_level="warning")


if __name__ == "__main__":
    main()
