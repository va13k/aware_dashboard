#!/usr/bin/env python3
"""Extract the table -> column list the AWARE Android client declares.

The client's providers are the authority on what Jdbc will send: it builds its
INSERT column list from TABLES_FIELDS, so any column the server lacks makes
every insert for that table fail silently.
"""
import glob
import json
import re
import sys



def array_elements(src, start):
    """Top-level elements of a Java array initialiser starting at the '{'."""
    depth, i, in_str, esc = 0, start, False, False
    cur, out = [], []
    while i < len(src):
        c = src[i]
        if in_str:
            cur.append(c)
            if esc:
                esc = False
            elif c == "\\":
                esc = True
            elif c == '"':
                in_str = False
            i += 1
            continue
        if c == '"':
            in_str = True
            cur.append(c)
        elif c in "{(":
            depth += 1
            if depth > 1:
                cur.append(c)
        elif c in "})":
            depth -= 1
            if depth == 0:
                out.append("".join(cur))
                return out
            cur.append(c)
        elif c == "," and depth == 1:
            out.append("".join(cur))
            cur = []
        else:
            cur.append(c)
        i += 1
    return out


def columns_of(entry, consts):
    """Column names in declaration order, skipping table constraints."""
    cols = []
    for _, ident in re.findall(r"(?:(\w+)\.)?(\w+)\s*\+\s*\"", entry):
        name = consts.get(ident)
        if name and name not in cols:
            cols.append(name)
    return cols


def extract(client_root):
    """table -> columns declared by the AWARE Android client's providers."""
    tables = {}
    for path in sorted(glob.glob(f"{client_root}/**/providers/*.java", recursive=True)):
        src = open(path, encoding="utf-8", errors="replace").read()
        consts = dict(re.findall(r'static final String\s+(\w+)\s*=\s*"([^"]+)"', src))
        dt = re.search(r"DATABASE_TABLES\s*=\s*\{", src)
        tf = re.search(r"TABLES_FIELDS\s*=\s*\{", src)
        if not dt or not tf:
            continue
        names = [n.strip().strip('"') for n in array_elements(src, dt.end() - 1) if n.strip()]
        fields = array_elements(src, tf.end() - 1)
        if len(names) != len(fields):
            print(f"WARN {path.split('/')[-1]}: {len(names)} tables vs {len(fields)} field blocks",
                  file=sys.stderr)
        for name, entry in zip(names, fields):
            cols = columns_of(entry, consts)
            if cols:
                tables[name] = cols
    return tables


if __name__ == "__main__":
    json.dump(extract(sys.argv[1] if len(sys.argv) > 1 else "."), sys.stdout, indent=1, sort_keys=True)
