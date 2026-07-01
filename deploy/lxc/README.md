# Streamva on Proxmox (LXC)

A native LXC install (no Docker) with a `systemd` service — the same convenient
shape as the [community-scripts.org](https://community-scripts.org/) helpers, but
runnable on *your* host today.

> **About community-scripts.org:** that's a curated GitHub project
> (`community-scripts/ProxmoxVE`). Getting Streamva *listed* there means opening a
> PR that follows their framework + criteria, and Streamva must be public on
> GitHub. These scripts give you the same one-command experience without waiting
> on that. (Happy to prep a submission later — see "Publishing" below.)

## Quick start (on the Proxmox host, as root)

**Interactive one-liner** (recommended) — auto-picks the next CT ID and prompts
for resources (Default/Advanced), like the community-scripts. You add your course
folders afterwards in the web UI:
```bash
bash -c "$(curl -fsSL https://raw.githubusercontent.com/rajat10cube/streamva/main/ct/streamva.sh)"
```

**Non-interactive / scriptable** — drive `create-lxc.sh` with env vars:
```bash
MEDIA_HOST=/mnt/pool/courses CTID=120 STREAMVA_AUTH_PASS='supersecret' \
  bash -c "$(curl -fsSL https://raw.githubusercontent.com/rajat10cube/streamva/main/deploy/lxc/create-lxc.sh)"
```

From a local clone (copies your local source instead of cloning the repo):
```bash
git clone https://github.com/rajat10cube/streamva && cd streamva
MEDIA_HOST=/mnt/pool/courses CTID=120 STREAMVA_REPO= bash deploy/lxc/create-lxc.sh
```

That creates a Debian 12 LXC, builds + installs Streamva, and starts it on
`http://<container-ip>:8000`. You then add course folders in the app (below).
(`create-lxc.sh` can optionally pre-mount a `MEDIA_HOST`; `ct/streamva.sh` does not.)

### Knobs (env vars for `create-lxc.sh`)
| Var | Default | Meaning |
|-----|---------|---------|
| `CTID` | *(required)* | unused container id, e.g. `120` |
| `MEDIA_HOST` | – | optional: host path to pre-mount read-only into the CT |
| `MEDIA_CT` | `/libraries/courses` | mount point inside the CT |
| `CT_HOSTNAME` | `streamva` | container hostname |
| `CORES` / `RAM_MB` / `DISK_GB` | `2` / `2048` / `10` | resources |
| `BRIDGE` / `STORAGE` | `vmbr0` / `local-lvm` | network / rootfs storage |
| `UNPRIVILEGED` | `1` | `0` = privileged (simplest for media perms) |
| `STREAMVA_REPO` | (repo) | set empty to copy local source instead of cloning |
| `STREAMVA_AUTH_PASS` | random | Basic-auth password |

## Adding your courses (in the app, like Jellyfin)
Courses are added from the **web UI → Libraries**. Two steps:

1. **Make the folder visible to the container** — bind-mount your host courses
   into the CT (read-only), then reboot it:
   ```bash
   pct set <CTID> -mp0 /mnt/pool/courses,mp=/mnt/courses,ro=1
   pct reboot <CTID>
   ```
   Add more sources with `-mp1`, `-mp2`, …
2. **Add it in Streamva** — open the app → **Libraries** → type or Browse to
   `/mnt/courses` → it scans automatically. Repeat for each folder.

**Unprivileged note:** if a mounted folder isn't readable inside the CT, on the
host run `chmod -R o+rX /mnt/pool/courses` (or recreate with `UNPRIVILEGED=0`).

## Day-2

```bash
pct exec 120 -- systemctl status streamva
pct exec 120 -- journalctl -u streamva -f          # logs
# rescan after adding courses:
curl -u admin:PASS -X POST http://<ip>:8000/api/admin/rescan
```

Put it behind your reverse proxy as usual — see [../../docs/DEPLOY.md](../../docs/DEPLOY.md).

## Install modes (interactive)
The one-liner shows a **Default / Advanced** menu:
- **Default** — sensible presets (2 cores / 2 GB / 10 GB, auto storage,
  unprivileged) and a **randomly generated admin password** (printed at the end).
- **Advanced** — set CT ID, hostname, cores, RAM, disk, storage, bridge,
  privileged/unprivileged, courses path, and password.

Your library config + password live in `/opt/streamva-data` (outside the app dir),
so updates never reset them.

## Update
Re-fetches the app and rebuilds; data/config/password are preserved.
```bash
pct exec <CTID> -- bash -c "$(curl -fsSL https://raw.githubusercontent.com/rajat10cube/streamva/main/deploy/lxc/update.sh)"
```

## Uninstall
```bash
# remove the app, keep your data:
pct exec <CTID> -- bash -c "$(curl -fsSL https://raw.githubusercontent.com/rajat10cube/streamva/main/deploy/lxc/uninstall.sh)"
# also delete data + service user:
pct exec <CTID> -- bash -c "$(curl -fsSL https://raw.githubusercontent.com/rajat10cube/streamva/main/deploy/lxc/uninstall.sh)" streamva --purge
# or remove the whole container from the host:
pct stop <CTID> && pct destroy <CTID>
```

## Manual install (existing container)
Already have a Debian/Ubuntu LXC? Just run the in-container installer:
```bash
STREAMVA_REPO=https://github.com/rajat10cube/streamva bash streamva-install.sh
```

## Publishing to community-scripts.org (optional, later)
To submit Streamva as an official helper script you'd: (1) make the repo public on
GitHub, (2) fork `community-scripts/ProxmoxVE`, (3) add `ct/streamva.sh` +
`install/streamva-install.sh` using their `build.func` framework and an app
metadata entry, (4) open a PR and pass their review. The logic here maps directly
onto that framework; ask and I'll adapt these into the PR layout.
