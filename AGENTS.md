# Agent guide

This is a static browser game. `index.html` loads the local Three.js library
from `vendor/three.min.js`, then starts `game.js`. The game has no backend,
package manifest, lockfile, build step, or model API. Its computer-controlled
players use local game code.

## Checks

- Run `python3 -m unittest discover -s tests -p 'test_*.py' -v` for fast
  offline checks. The tests use only the Python standard library.
- Run `git diff --check` to check patch whitespace.
- To play the game locally, run `python3 -m http.server 8777 --bind 127.0.0.1`
  from the repository root, then open `http://127.0.0.1:8777/`. Stop the
  server when finished.

Keep the runtime scripts local and load Three.js before `game.js`. Do not add a
remote runtime service or package manager without a clear need. Preserve the
existing public game URL and game behavior unless the owner asks for a change.
