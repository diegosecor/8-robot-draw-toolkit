# Robot Draw Toolkit

`>>> DIEGO: WRITE THIS <<<`

## What the skill does and when it triggers

`>>> DIEGO: WRITE THIS <<<`

## What the MCP tool does

`>>> DIEGO: WRITE THIS <<<`

## The friction that motivated each

### The skill (scope-check)

`>>> DIEGO: WRITE THIS <<<`

### The MCP tool (search_robot_papers)

`>>> DIEGO: WRITE THIS <<<`

## Technical setup

How to install both pieces: dependencies, the paper index, the server registration and the skill.
Everything runs locally, with no API keys and no paid services.

### Versions

Tested on Windows 11. Versions are pinned in `mcp_server/requirements.txt`.

| Component | Version |
|---|---|
| Python | 3.14.7 |
| `mcp` (official MCP Python SDK) | 2.3.0 |
| `chromadb` | 1.5.9 |
| `fastembed` | 0.9.0 |
| `pypdf` | 6.20.1 |
| Embedding model | `sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2` (through FastEmbed) |

### Repository layout

```
.claude/skills/scope-check/     the checker skill: SKILL.md + references/robot-params.md
.claude/skills/hello-check/     trivial skill, used only to confirm that skills are loaded
mcp_server/server.py            the MCP server (stdio), one tool: search_robot_papers
mcp_server/fetch_sources.py     downloads the sources into data/papers/
mcp_server/ingest.py            builds the local index from the files in data/papers/
mcp_server/sources.csv          the sources: title, authors, year, venue, link, license note
mcp_server/requirements.txt     pinned dependencies
.mcp.json                       Claude Code registration (machine-specific paths, see below)
tests/                          unit tests, search tests and an MCP stdio test
data/                           local only, not committed: papers, index, model cache
```

### 1. Install the dependencies

From PowerShell:

```
git clone https://github.com/diegosecor/8-robot-draw-toolkit.git
cd 8-robot-draw-toolkit
python -m venv .venv
.venv\Scripts\python.exe -m pip install -r mcp_server\requirements.txt
```

### 2. Get the sources

The papers and manuals are copyrighted, so they are not in the repository (`data/` is gitignored).
Every source in `mcp_server/sources.csv` links to an open-access copy (its `license_note` column
says where it comes from). This script downloads them into `data/papers/` for local use:

```
.venv\Scripts\python.exe mcp_server\fetch_sources.py
```

It fetches the PDFs, and the Robot Components documentation pinned to the commits the index was
built from. It keeps files that already exist, so it can be run again. In the author's test on
2026-11-06 it took about 1.5 minutes, and the files it downloaded were byte-identical to the ones
used to build the index.

Two cases need a browser:

- `gleeson2022_spray_trajectories`: IEEE refused the scripted download (HTTP 418). The script
  prints the link; save the PDF as `data/papers/gleeson2022_spray_trajectories.pdf`.
- `levy2002_lscm`, `braumann2011_parametric_robot_control` and `garcia2019_robot_ex_machina` have
  no direct PDF link and were not in the author's index either. They are optional.

`ingest.py` skips sources without a file and lists them at the end of its run.

### 3. Build the index

```
.venv\Scripts\python.exe mcp_server\ingest.py
```

The first run downloads the embedding model into `data/model-cache/` (about 240 MB), so it needs
internet once; after that everything works offline. The index is stored in `data/chroma_store/`.
With 26 sources (all but the three optional ones) it holds 3,493 passages. Running it again only embeds new or changed
sources; `--rebuild` starts from scratch.

### 4. Run the tests

```
.venv\Scripts\python.exe -m unittest discover -s tests -v
```

There are 30 tests; the download tests mock the network. The search, stdio and minimal-environment
tests are skipped until the index exists.

### 5. Register the MCP server

**Machine-specific:** replace `<REPO_ROOT>` with the absolute path of your clone, using forward
slashes, for example `C:/Users/you/8-robot-draw-toolkit`. Both paths must be absolute.

**Claude Code** reads `.mcp.json` at the repository root (project scope). The committed file holds
the author's paths; replace them with yours:

```json
{
  "mcpServers": {
    "robot-draw-toolkit": {
      "type": "stdio",
      "command": "<REPO_ROOT>/.venv/Scripts/python.exe",
      "args": ["<REPO_ROOT>/mcp_server/server.py"]
    }
  }
}
```

Open a new session in the repository, approve the project server when asked, and check that `/mcp`
lists `robot-draw-toolkit`.

**Codex** (the CLI, the IDE extension and the desktop app share `~/.codex/config.toml`): add

```toml
[mcp_servers.robot-draw-toolkit]
command = "<REPO_ROOT>/.venv/Scripts/python.exe"
args = ["<REPO_ROOT>/mcp_server/server.py"]
```

or, in the desktop app, use Settings → MCP servers → Add server (STDIO). Restart Codex and check
`/mcp`.

The server logs to stderr only, never to stdout. If the client starts it without `USERPROFILE`,
it uses `data/` as its home directory.

### 6. Install the skill

- **Claude Code:** copy `.claude/skills/scope-check/` into the `.claude/skills/` folder of the
  project you want to check, or into `~/.claude/skills/` for every project. Run it with
  `/scope-check`, or let the agent load it from its description.
- **Codex:** the Codex documentation lists `.agents/skills/` (repository) and `~/.agents/skills/`
  (user) as skill folders. Copy the same `scope-check` folder there and run it with `$scope-check`.

The skill only reads: it needs `git` and a git repository with the changes to check.

## Which tools I confirmed it works in

`>>> DIEGO: WRITE THIS <<<`

## Borrowed or adapted

`>>> DIEGO: WRITE THIS <<<`

## How I used AI on this assignment

`>>> DIEGO: WRITE THIS <<<`
