# The tests of ../python.yaml: a line under `ruleid:` must match, a line under `ok:` must not.
import os
import pickle
import ssl
import subprocess
import tempfile

import httpx
import requests
import yaml


def evals(text):
    # ruleid: crissp-py-eval
    eval(text)
    # ruleid: crissp-py-eval
    exec(text, {})
    # ok: crissp-py-eval
    eval("1 + 1")


def shells(name):
    # ruleid: crissp-py-shell
    subprocess.run("ls " + name, shell=True)
    # ruleid: crissp-py-shell
    subprocess.check_output(f"cat {name}", shell=True)
    # ruleid: crissp-py-shell
    os.system(name)
    # ok: crissp-py-shell
    subprocess.run(["ls", name])
    # ok: crissp-py-shell
    subprocess.run("ls -l", shell=True)


def yamls(text):
    # ruleid: crissp-py-yaml-load
    yaml.load(text)
    # ruleid: crissp-py-yaml-load
    yaml.load(text, Loader=yaml.Loader)
    # ruleid: crissp-py-yaml-load
    yaml.unsafe_load(text)
    # ok: crissp-py-yaml-load
    yaml.load(text, Loader=yaml.SafeLoader)
    # ok: crissp-py-yaml-load
    yaml.safe_load(text)


def tls(url):
    # ruleid: crissp-py-tls-off
    requests.get(url, verify=False)
    # ruleid: crissp-py-tls-off
    httpx.post(url, json={}, verify=False)
    # ruleid: crissp-py-tls-off
    ssl._create_unverified_context()
    # ok: crissp-py-tls-off
    requests.get(url, timeout=5)


def servers(app):
    # ruleid: crissp-py-debug-server
    app.run(host="0.0.0.0", debug=True)
    # ok: crissp-py-debug-server
    app.run(host="127.0.0.1")


def loads(blob, path):
    # ruleid: crissp-py-pickle
    pickle.loads(blob)
    # ruleid: crissp-py-pickle
    pickle.load(open(path, "rb"))
    # ok: crissp-py-pickle
    pickle.dumps(blob)


def queries(cur, name):
    # ruleid: crissp-py-sql-string
    cur.execute(f"SELECT * FROM users WHERE name = '{name}'")
    # ruleid: crissp-py-sql-string
    cur.execute("SELECT * FROM users WHERE name = '%s'" % name)
    # ruleid: crissp-py-sql-string
    cur.execute("SELECT * FROM users WHERE name = '" + name + "'")
    # ok: crissp-py-sql-string
    cur.execute("SELECT * FROM users WHERE name = ?", (name,))


def temp():
    # ruleid: crissp-py-mktemp
    tempfile.mktemp()
    # ok: crissp-py-mktemp
    tempfile.mkstemp()
