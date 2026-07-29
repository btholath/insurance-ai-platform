# Local Setup — WSL/Ubuntu

Everything needed to go from a bare WSL/Ubuntu shell to a working
Spec-Driven Development environment for this project, using GitHub
Spec Kit + Claude Code. Every command below was actually run and
verified in this project's setup session — this isn't a generic guide,
it's what happened, including the two real problems that came up and
how they were fixed.

---

## 1. Prerequisites

- Windows 11 with WSL2 enabled, Ubuntu installed as the distro
- A GitHub account (for later — pushing this repo)
- A Claude account with an active **Pro, Max, Team, or Enterprise**
  plan (the free Claude.ai plan does **not** include Claude Code)

Check you're in a working Ubuntu shell:

```bash
lsb_release -a
```

---

## 2. Install `uv` (Python package/tool manager)

Spec Kit's CLI is distributed as a `uv` tool, not via `pip` directly.

```bash
curl -LsSf https://astral.sh/uv/install.sh | sh
```

```bash
source $HOME/.local/bin/env
```

```bash
which uv
```

**Expect**: a path like `/home/<you>/.local/bin/uv`

```bash
uv --version
```

---

## 3. Install the `specify` CLI (GitHub Spec Kit)

```bash
uv tool install specify-cli --from git+https://github.com/github/spec-kit.git
```

This pulls from GitHub directly (not a package index), so it can take
a few minutes.

```bash
which specify
```

**Expect**: a path like `/home/<you>/.local/bin/specify`

> **⚠ If `specify: command not found` after install**, `uv tool
install` puts binaries in `~/.local/bin`, and that directory isn't
> always on `PATH` yet. Fix:
>
> ```bash
> uv tool update-shell
> source ~/.bashrc
> which specify
> ```
>
> If still not found, check it's actually there and add it to `PATH`
> manually:
>
> ```bash
> ls ~/.local/bin/ | grep specify
> echo 'export PATH="$HOME/.local/bin:$PATH"' >> ~/.bashrc
> source ~/.bashrc
> which specify
> ```

Verify the environment Spec Kit will use:

```bash
specify check
```

**Expect**: a table of detectable coding-agent CLIs/IDEs. You mainly
care that **Claude Code** and **Visual Studio Code** show as
`(available)` — everything else showing `(not found)` is normal and
expected if you're not using those tools.

---

## 4. Create the project and initialize Spec Kit

```bash
cd ~
mkdir insurance-ai-platform && cd insurance-ai-platform
code .
```

The last command opens the folder in VS Code via the WSL extension. If
`code .` doesn't work, open VS Code manually and use "Connect to WSL"
from the command palette, then open this folder.

Initialize Spec Kit into the current directory, targeting Claude Code
as the integration:

```bash
specify init . --integration claude
```

You'll be prompted for a script type — choose **`sh` (POSIX Shell)**,
the default, since we're on bash in WSL:

```
▶    sh (POSIX Shell (bash/zsh))
```

Just press Enter to accept it.

If the directory already has files in it (e.g. this README, or the
BRD), you'll see:

```
Warning: Current directory is not empty (2 items)
Template files will be merged with existing content and may overwrite
existing files. Do you want to continue? [y/N]: y
```

Answer `y` — it merges, it doesn't wipe your existing files.

**Expect** at the end:

```
Project ready.
```

plus a "Next Steps" panel listing the available `/speckit-*` commands.

Confirm the scaffold:

```bash
ls -la
ls -la .specify/
ls -la .claude/
```

**Expect**: `.specify/` containing `memory/`, `scripts/`, `templates/`,
`workflows/`, `init-options.json`, `integration.json`; `.claude/`
containing `skills/`.

List exactly which Spec Kit skills got installed:

```bash
ls .claude/skills/
```

**Expect** (10 skills):

```
speckit-analyze     speckit-clarify        speckit-converge
speckit-checklist   speckit-constitution   speckit-implement
speckit-plan        speckit-specify        speckit-tasks
speckit-taskstoissues
```

---

## 5. Set up git — **before** your first commit, not after

The Spec Kit installer itself warns about this: `.claude/` can contain
credentials/auth tokens, so it must be gitignored from the start.

```bash
git init
git branch -M main
```

```bash
cat > .gitignore << 'EOF'
.claude/
.env
.env.staging
__pycache__/
*.pyc
node_modules/
EOF
```

```bash
git add .
git status
```

**Verify**: `.claude/` does **not** appear anywhere in the staged file
list before you commit. If it does, stop and fix `.gitignore` first.

```bash
git commit -m "Initial Spec Kit scaffold for insurance-ai-platform"
```

---

## 6. Install and authenticate Claude Code

```bash
sudo apt update
curl -fsSL https://claude.ai/install.sh | bash
```

(or via npm, if you prefer: `npm install -g @anthropic-ai/claude-code`)

### ⚠ The most important gotcha in this whole setup: authentication method

Claude Code can authenticate two completely different ways:

- **Subscription login (OAuth)** — uses your Pro/Max/Team/Enterprise
  plan, no extra charge beyond your monthly subscription.
- **API key** — bills per-token against a separate Anthropic Console
  account, **on top of** whatever you pay for Pro.

If an `ANTHROPIC_API_KEY` environment variable is set **anywhere** on
your system, Claude Code silently prefers it over your subscription —
even if you're already logged in with your Pro account. This actually
happened during this project's setup and would have billed API usage
instead of using the Pro plan already being paid for, until caught.

**Always check before your first real session:**

```bash
echo $ANTHROPIC_API_KEY
```

**Expect**: empty output. If it prints a key (starts with `sk-ant-`),
find and remove it:

```bash
grep -rn "ANTHROPIC_API_KEY" ~/.bashrc ~/.zshrc ~/.profile ~/.bash_profile 2>/dev/null
```

Comment out or delete whatever line that turns up, then:

```bash
unset ANTHROPIC_API_KEY
source ~/.bashrc
echo $ANTHROPIC_API_KEY
```

**Expect now**: empty.

Then log in cleanly:

```bash
claude
```

Inside the session:

```
/logout
```

```
/login
```

Choose the **Claude.ai account** option (not "Anthropic Console"). A
browser window opens — sign in with your normal claude.ai account, the
one with your paid plan.

**Always verify which method is actually active before doing real
work:**

```
/status
```

**Expect**: `Auth token:` populated (not `none`), and no `API key:` row
showing `ANTHROPIC_API_KEY`. The top status bar in the Claude Code UI
should show something like `Sonnet 5 · Claude Pro · <your-email>'s
Organization` — **not** `API Usage Billing`. If it says "API Usage
Billing," stop and redo the logout/login steps above before
approving any file writes.

---

## 7. Run the constitution step

Inside a `claude` session, in the project directory:

```
/speckit-constitution <your project principles, stack, and constraints>
```

The exact prompt used for this project (adjust for your own if you're
following this as a template):

```
/speckit-constitution Local-first AI Insurance Risk & Fraud Intelligence
Platform, based on README-Business-Requirements-Document.md in this
repo. Stack: Python 3.13, Django 5.x, DRF, PostgreSQL 16+, Redis,
Celery, Ollama (Llama 3/Mistral/DeepSeek), pgvector. Runs entirely on
WSL Ubuntu, no cloud dependencies. Every module needs audit logging,
role-based access, and explainable AI outputs. Testing: pytest +
Factory Boy, coverage required for business-rule code (risk scoring,
fraud detection). Phase 0 (Streamlit spike) is disposable prototyping,
not spec-driven — do not scaffold it as a formal module.
```

It will show you a diff/write of `.specify/memory/constitution.md` and
ask for approval:

```
Do you want to overwrite constitution.md?
1. Yes
2. Yes, allow all edits during this session
3. No
```

For your **first** session with a new tool, pick **`1. Yes`** — approve
writes one at a time so you can see what it's actually touching. Once
you're comfortable with the tool's behavior, `2` speeds things up by
skipping repeat prompts for the rest of that session.

Review what it generated:

```bash
cat .specify/memory/constitution.md
```

**Sanity-check the output, don't just trust it blindly** — in this
project's actual run, the first draft had two real mistakes worth
watching for in your own runs:

1. It referenced slash commands with **dot** notation
   (`/speckit.specify`) instead of the **hyphen** notation the actual
   installed CLI uses (`/speckit-specify`). Check
   `ls .claude/skills/` against what the constitution says — they must
   match.
2. It referenced a `/code-review` skill that was never actually
   installed. Verify every tool/skill name a generated doc mentions
   really exists:
   ```bash
   ls .claude/skills/
   ```

If you find similar mismatches, fix them the same way — through the
tool itself, not manual edits, so the version/changelog stays accurate:

```
/speckit-constitution Fix <describe the specific inaccuracy>. This is
a PATCH-level clarification, not a principle change.
```

Check the version bumped correctly at the bottom of the file
(`**Version**: X.Y.Z`) — a wording/reference fix should be a **PATCH**
bump (e.g. `1.0.0 → 1.0.1`), not MINOR or MAJOR.

Exit and commit:

```bash
exit
```

```bash
git add .
git commit -m "Ratify project constitution"
```

---

## 8. Quick reference — full command sequence, start to finish

```bash
# Install uv
curl -LsSf https://astral.sh/uv/install.sh | sh
source $HOME/.local/bin/env

# Install Spec Kit CLI
uv tool install specify-cli --from git+https://github.com/github/spec-kit.git
specify check

# Create and scaffold the project
mkdir ~/insurance-ai-platform && cd ~/insurance-ai-platform
code .
specify init . --integration claude   # choose "sh" when prompted

# Git, with .claude/ excluded BEFORE first commit
git init
git branch -M main
cat > .gitignore << 'EOF'
.claude/
.env
.env.staging
__pycache__/
*.pyc
node_modules/
EOF
git add .
git status                             # confirm .claude/ is NOT listed
git commit -m "Initial Spec Kit scaffold"

# Install Claude Code
curl -fsSL https://claude.ai/install.sh | bash

# Confirm no stray API key will hijack billing
echo $ANTHROPIC_API_KEY                # must be empty
claude
#   /logout
#   /login              -> choose Claude.ai account, NOT Console
#   /status             -> confirm Pro plan is active, not an API key

# Ratify the constitution
#   /speckit-constitution <your project's principles/stack/constraints>
#   review output, fix any inaccuracies, confirm PATCH/MINOR/MAJOR bump is correct
exit
git add .
git commit -m "Ratify project constitution"
```

---

## 9. What's next

With the constitution ratified, the project forks into two independent
tracks (per Principle VI of the constitution — disposable prototyping
is explicitly kept out of the Spec Kit lifecycle):

- **Phase 0 — Streamlit spike**: built directly, by hand, outside Spec
  Kit entirely. Validates the Ollama + prompt-quality assumptions
  before committing to a real spec.
- **Phase 1 onward — the real platform**: each module goes through the
  full `/speckit-specify` → `/speckit-plan` → `/speckit-tasks` →
  `/speckit-implement` cycle, one module at a time, per the roadmap in
  `README-Business-Requirements-Document.md`.

See `README-Business-Requirements-Document.md` §13 for the full phase
roadmap.
