---
applyTo: '**'
---

# Shell Execution

Only two things order shell commands: one consumes another's output, or both touch the same file or resource. A synchronous command returns its output in the same call but blocks until it exits; an async command runs in its own terminal alongside other work and notifies on completion or when it needs input.

Run a command synchronously only when it is short and the very next step needs its output. Run every other command async, and until it notifies, continue work that needs none of its output instead of polling or sleeping.
