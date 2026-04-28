import argparse
import datetime
import json
import os
import re
import subprocess
import glob


def find_manifest():
    matches = glob.glob("custom_components/*/manifest.json")
    return matches[0] if matches else None


def get_current_version(manifest_path):
    try:
        tags = (
            subprocess.check_output(["git", "tag"], stderr=subprocess.DEVNULL)
            .decode()
            .splitlines()
        )
        v_tags = []
        for tag in tags:
            tag = tag.strip()
            match = re.match(r"^(\d+)\.(\d+)\.(\d+)(?:(b)(\d+)|(-dev)(\d+))?$", tag)
            if match:
                y, m, p, bp, bn, dp, dn = match.groups()
                v_tags.append(
                    {
                        "tag": tag,
                        "key": (
                            int(y),
                            int(m),
                            int(p),
                            (1 if bp else (0 if dp else 2)),
                            (int(bn) if bp else (int(dn) if dp else 0)),
                        ),
                    }
                )
        if v_tags:
            return sorted(v_tags, key=lambda x: x["key"], reverse=True)[0]["tag"]
    except (subprocess.CalledProcessError, IndexError, ValueError):
        pass
    if manifest_path and os.path.exists(manifest_path):
        with open(manifest_path, "r") as f:
            return json.load(f).get("version", "2026.1.0")
    return "2026.1.0"


def write_version(v, manifest_path):
    with open("VERSION", "w") as f:
        f.write(v)
    if manifest_path and os.path.exists(manifest_path):
        with open(manifest_path, "r") as f:
            data = json.load(f)
        data["version"] = v
        with open(manifest_path, "w") as f:
            json.dump(data, f, indent=2)
            f.write("\n")


def calculate_version(bump_type, is_beta, is_dev, curr):
    match = re.match(r"^(\d+)\.(\d+)\.(\d+)(?:(b)(\d+)|(-dev)(\d+))?$", curr)
    if not match:
        return "1.0.0"
    
    major, minor, patch, b_p, b_n, d_p, d_n = match.groups()
    major, minor, patch = int(major), int(minor), int(patch)
    
    # Handle existing beta/dev suffix
    stype, snum = (
        ("b", int(b_n)) if b_p else (("-dev", int(d_n)) if d_p else (None, 0))
    )

    if is_dev:
        # For dev, we usually just bump the dev number if already on dev,
        # or bump patch and start dev0
        if stype == "-dev":
            return f"{major}.{minor}.{patch}-dev{snum+1}"
        return f"{major}.{minor}.{patch+1}-dev0"

    if is_beta:
        if stype == "b":
            # Just increment beta number
            return f"{major}.{minor}.{patch}b{snum+1}"
        
        # New beta: bump version according to type and start b0
        if bump_type == "major":
            return f"{major+1}.0.0b0"
        elif bump_type == "minor":
            return f"{major}.{minor+1}.0b0"
        else: # patch
            return f"{major}.{minor}.{patch+1}b0"

    # Stable release
    if stype:
        # If we were on beta/dev, "stable" means just removing the suffix
        return f"{major}.{minor}.{patch}"
    
    # Otherwise bump normally
    if bump_type == "major":
        return f"{major+1}.0.0"
    elif bump_type == "minor":
        return f"{major}.{minor+1}.0"
    else: # patch
        return f"{major}.{minor}.{patch+1}"


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("action", choices=["get", "bump"])
    parser.add_argument("--bump", choices=["major", "minor", "patch"], default="patch")
    parser.add_argument("--beta", action="store_true")
    parser.add_argument("--dev", action="store_true")
    parser.add_argument("--manifest", default=None)
    args = parser.parse_args()
    m_path = args.manifest or find_manifest()
    if args.action == "get":
        print(get_current_version(m_path))
    elif args.action == "bump":
        v = calculate_version(args.bump, args.beta, args.dev, get_current_version(m_path))
        write_version(v, m_path)
        print(v)
