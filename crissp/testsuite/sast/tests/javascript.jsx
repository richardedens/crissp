// The tests of ../javascript.yaml: a line under `ruleid:` must match, a line under `ok:` must not.
import { exec } from "child_process";
import * as cp from "child_process";

export function evals(text, el) {
  // ruleid: crissp-js-eval
  eval(text);
  // ruleid: crissp-js-eval
  const f = new Function("a", text);
  // ruleid: crissp-js-eval
  setTimeout("run(" + text + ")", 10);
  // ok: crissp-js-eval
  setTimeout(() => el.focus(), 10);
  // ok: crissp-js-eval
  setInterval(tick, 1000);
  return f;
}

export function html(el, name) {
  // ruleid: crissp-js-html-injection
  el.innerHTML = "<b>" + name + "</b>";
  // ruleid: crissp-js-html-injection
  el.innerHTML = `<b>${name}</b>`;
  // ruleid: crissp-js-html-injection
  el.insertAdjacentHTML("beforeend", name);
  // ruleid: crissp-js-html-injection
  document.write(name);
  // ok: crissp-js-html-injection
  el.innerHTML = "";
  // ok: crissp-js-html-injection
  el.textContent = name;
}

export function Card({ body }) {
  // ruleid: crissp-react-dangerous-html
  return <div dangerouslySetInnerHTML={{ __html: body }} />;
}

export function Safe({ body }) {
  // ok: crissp-react-dangerous-html
  return <div>{body}</div>;
}

export function shells(name) {
  // ruleid: crissp-js-shell
  exec("ls " + name);
  // ruleid: crissp-js-shell
  cp.execSync(`cat ${name}`);
  // ok: crissp-js-shell
  cp.execFile("ls", [name]);
  // ok: crissp-js-shell
  exec("ls -l");
}

export function tls(https, url) {
  // ruleid: crissp-js-tls-off
  https.get(url, { rejectUnauthorized: false });
  // ruleid: crissp-js-tls-off
  process.env.NODE_TLS_REJECT_UNAUTHORIZED = "0";
  // ok: crissp-js-tls-off
  https.get(url, { timeout: 5000 });
}
