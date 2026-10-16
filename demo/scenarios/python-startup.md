# Python resource startup exercise

Run `npm run demo:python-startup` from the Engineering Guard root. The command
checks that the original Python baseline fails because it leaves a connection
open after initialization fails and loses cleanup-error context, while the corrected reference passes all
tests. Neither result evaluates whether an agent followed the skill.

For an Implement exercise, copy `demo/python/startup/` to a disposable directory
outside this repository, replace `fixed.py` with `before.py` in that copy (keep
the module name `fixed.py`), then run
`python3 -B -m unittest discover -s . -p 'test_startup.py'` from that directory.
Ask `$engineering-guard-implement` to fix startup cleanup, preserve the
original initialization error if cleanup also fails, and run the tests.
The successful call leaves the connection open for its caller to close.
