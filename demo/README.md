# Demo fixtures

The code in this directory is deliberately defective or vulnerable. It exists to show how the Engineering Guard skills react to bad code and to check that the demonstrations fail where they are expected to.

- `src/` (the checkout demo) charges the wrong amount on purpose, so `npm run demo:behavior` is expected to fail.
- `security/vulnerable/` allows cross-user access on purpose; `security/fixed/` is the corrected counterpart.

Do not fix these fixtures, and do not report them as vulnerabilities in Engineering Guard. See the top-level `README.md` ("Deterministic demonstrations") for what each demo checks.
