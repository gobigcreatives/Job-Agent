# Running this on your own computer

The Claude Code cloud environment this project was built in only allows
network access to a fixed allowlist of known services — which blocks
smaller third-party APIs like Serper. Your own computer has normal
internet access, so everything works there. This is a step-by-step guide
assuming no prior command-line experience.

## 1. Install the prerequisites (one-time)

- **Python 3.11 or newer**: https://www.python.org/downloads/ (on the
  install screen, tick "Add Python to PATH" if you're on Windows).
- **Git**: https://git-scm.com/downloads

## 2. Open a terminal

- **Mac**: open the "Terminal" app (search for it with Spotlight, Cmd+Space).
- **Windows**: open "PowerShell" (search for it in the Start menu).
- **Linux**: open your terminal application.

## 3. Get the code and your personal files

If someone sent you a `.zip` of this project, extract it and skip to step
4. Otherwise, clone it from GitHub:

```bash
git clone https://github.com/gobigcreatives/Job-Agent.git
cd Job-Agent
git checkout claude/autonomous-job-discovery-n97wn6
```

Then copy your `.env` file (your API keys) and `config/profile.yaml`,
`config/preferences.yaml`, `config/resume.md` (your details) into this
folder — these were never pushed to GitHub on purpose (they're personal),
so they need to be copied in separately from wherever you saved them.

## 4. Install and run — one command

```bash
bash run.sh
```

This installs everything it needs (first time only takes a minute or two)
and then runs a **dry run**: it discovers and scores jobs but doesn't
apply to anything, so it's safe to run as many times as you like.

When you're happy with the matches it's finding, run it for real — this
lets it actually tailor CVs, generate cover letters, and apply to strong
matches:

```bash
bash run.sh --live
```

If `bash` isn't recognized (some Windows setups), run the two commands
inside it manually instead:

```bash
pip install -e ".[dev]"
playwright install chromium
jobagent run --dry-run
```

## Other useful commands

```bash
jobagent report          # reprint the last run's summary
jobagent pending         # list application questions waiting on you
jobagent answer 3 "..."  # answer one
jobagent schedule        # see the cron expression for running this automatically on a schedule
```

See the main [README](README.md) for what each config file controls and
how the safety limits work.
