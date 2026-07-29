
## Set it up in WSL/Ubuntu

```bash
cd ~
mkdir insurance-ai-platform && cd insurance-ai-platform
code .
```

That last command opens the folder directly in VS Code (assuming you have the WSL extension installed and `code` on your PATH — if `code .` doesn't work, open VS Code manually and use "Connect to WSL" from the command palette, then open this folder).

Then this is the same directory where you'd run `specify init` next — worth doing that before your first commit so `.specify/` and the Claude Code integration are part of the initial repo state, not bolted on after:

```bash
specify init . --integration claude
```
(using `.` instead of a new subdirectory name, since you're already inside the folder)

And when you get to creating the GitHub repo later, reuse the same name for consistency:

```bash
gh repo create insurance-ai-platform --private --source=. --remote=origin
```

One thing worth deciding now rather than later: **public or private?** Given this contains an uploaded dataset with realistic-looking client PII fields (names, emails, phone numbers) even if synthetic, I'd lean private for the repo unless you're confident the CSV data is fully synthetic and fine to publish — happy to help you check/scrub that before it goes public if that matters to you.