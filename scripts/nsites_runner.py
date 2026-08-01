#!/usr/bin/env python3
"""N-sites portable runner — the worker contract from the N-Sites Framework.

Every site is a disposable worker; state lives in HF Datasets / D1 / Git.
Contract: pull -> run -> push -> FAIL CLOSED.
A worker that cannot complete records INCOMPLETE, never pass.

Usage:
    python3 scripts/nsites_runner.py --job airbench_snapshot
    python3 scripts/nsites_runner.py --sites          # print site registry
    python3 scripts/nsites_runner.py --validate       # check config + reachability

Zero hard deps: stdlib only. huggingface_hub used opportunistically if present.
"""
import argparse
import json
import os
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CONFIG = ROOT / "nsites_sites.json"
RUNS_LOG = ROOT / "runner_runs.jsonl"


def load_config():
    with open(CONFIG) as f:
        return json.load(f)


def record_run(job_name, site, status, detail, started):
    """Append the run record. FAIL CLOSED: status is only ever
    COMPLETE or INCOMPLETE — this file never writes 'pass'."""
    rec = {
        "job": job_name,
        "site": site,
        "status": status,  # COMPLETE | INCOMPLETE
        "detail": detail[-2000:],
        "started_at": datetime.fromtimestamp(started, timezone.utc).isoformat(),
        "finished_at": datetime.now(timezone.utc).isoformat(),
    }
    with open(RUNS_LOG, "a") as f:
        f.write(json.dumps(rec) + "\n")
    return rec


def sh(cmd, timeout=600, shell=True):
    return subprocess.run(
        cmd, shell=shell, capture_output=True, text=True, timeout=timeout
    )


def run_job(cfg, job_name):
    jobs = cfg.get("jobs", {})
    if job_name not in jobs:
        print(f"unknown job: {job_name} (have: {', '.join(jobs)})", file=sys.stderr)
        return 2
    job = jobs[job_name]
    site = job["site"]
    started = time.time()
    log = []

    try:
        # ---- PULL ----
        for step in job.get("pull", []):
            kind, _, ref = step.partition(":")
            if kind == "git":
                r = sh(f"git -C {ROOT} pull --ff-only origin {ref}")
                log.append(f"pull git:{ref} rc={r.returncode}")
                if r.returncode != 0:
                    raise RuntimeError(f"git pull failed: {r.stderr[-500:]}")
            elif kind == "env":
                if site != "local_m4" and cfg["sites"].get(site, {}).get("ssh") and not _am_i(site, cfg):
                    # remote site: verify the env file over SSH, not locally
                    ssh = cfg["sites"][site]["ssh"]
                    r = sh(f"ssh -o BatchMode=yes -o ConnectTimeout=20 {ssh} 'test -f {ref}'", timeout=30)
                    if r.returncode != 0:
                        raise RuntimeError(f"env file missing on {site}: {ref}")
                elif not Path(os.path.expanduser(ref)).exists():
                    raise RuntimeError(f"env file missing: {ref}")
                log.append(f"pull env:{ref} ok")

        # ---- RUN ----
        cmd = job["run"]
        if site == "oracle_micro_2" and not _am_i(site, cfg):
            ssh = cfg["sites"][site]["ssh"]
            r = sh(
                f"ssh -o BatchMode=yes -o ConnectTimeout=20 {ssh} "
                f"'source ~/.airbench_env && {cmd}'",
                timeout=job.get("timeout", 900),
            )
        else:
            r = sh(cmd, timeout=job.get("timeout", 900))
        log.append(f"run rc={r.returncode} out={r.stdout[-300:]}")
        if r.returncode != 0:
            raise RuntimeError(f"run failed: {r.stderr[-500:]}")

        # ---- PUSH ----
        for step in job.get("push", []):
            kind, _, ref = step.partition(":")
            if kind.startswith("hf_"):
                store = cfg["state_stores"][kind]
                _hf_push(store, ref, log)
            elif kind == "git":
                r = sh(f"git -C {ROOT} push {cfg['state_stores']['git']['remote']} {ref}")
                log.append(f"push git:{ref} rc={r.returncode}")
                if r.returncode != 0:
                    raise RuntimeError(f"git push failed: {r.stderr[-500:]}")
            else:
                log.append(f"push {kind}: handled externally")

    except Exception as e:  # FAIL CLOSED
        rec = record_run(job_name, site, "INCOMPLETE", str(e) + " | " + " ; ".join(log), started)
        print(f"INCOMPLETE: {rec['detail'][:300]}", file=sys.stderr)
        return 1

    rec = record_run(job_name, site, "COMPLETE", " ; ".join(log), started)
    print(f"COMPLETE: {job_name} on {site}")
    return 0


def _am_i(site, cfg):
    """True if we are already on the target box (hostname match)."""
    if site.startswith("oracle"):
        try:
            host = subprocess.run(["hostname"], capture_output=True, text=True).stdout.strip()
            return site.replace("_", "-") in host or host in site
        except Exception:
            return False
    return site in ("local_m4", "github_actions")


def _hf_push(store, path_in_repo, log):
    try:
        from huggingface_hub import HfApi
    except ImportError:
        raise RuntimeError("huggingface_hub not installed on this worker")
    token = os.environ.get("HF_TOKEN")
    if not token:
        raise RuntimeError("HF_TOKEN missing")
    local = ROOT / path_in_repo
    if not local.exists():
        raise RuntimeError(f"artifact missing: {local}")
    HfApi(token=token).upload_file(
        path_or_fileobj=str(local), path_in_repo=path_in_repo,
        repo_id=store["repo"], repo_type=store["repo_type"],
        commit_message=f"nsites_runner push {path_in_repo}",
    )
    log.append(f"push hf:{store['repo']}/{path_in_repo} ok")


def validate(cfg):
    ok = True
    print(f"canon gate_date: {cfg['canon']['gate_date']}")
    for name, s in cfg["sites"].items():
        line = f"  {name:16s} {s['status']:10s} {s['role']}"
        if s.get("ssh"):
            r = sh(f"ssh -o BatchMode=yes -o ConnectTimeout=10 {s['ssh']} true", timeout=20)
            line += f"  ssh={'ok' if r.returncode == 0 else 'FAIL'}"
            ok = ok and r.returncode == 0
        print(line)
    for name in cfg["jobs"]:
        j = cfg["jobs"][name]
        site_ok = j["site"] in cfg["sites"]
        print(f"  job {name:18s} site={j['site']} cfg={'ok' if site_ok else 'BROKEN'}")
        ok = ok and site_ok
    print("VALID" if ok else "INVALID")
    return 0 if ok else 1


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--job")
    ap.add_argument("--sites", action="store_true")
    ap.add_argument("--validate", action="store_true")
    a = ap.parse_args()
    cfg = load_config()
    if a.sites:
        print(json.dumps(cfg["sites"], indent=2))
        return 0
    if a.validate:
        return validate(cfg)
    if a.job:
        return run_job(cfg, a.job)
    ap.print_help()
    return 2


if __name__ == "__main__":
    sys.exit(main())
