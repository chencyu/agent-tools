---
applyTo: '**'
---

# Parallel by Default

Your default is to issue one call, wait for its result, then decide the next; override that default. A call whose inputs you already hold gains nothing by waiting, and each response spent on a call that could have joined others costs a full round trip. Only two things order calls: one consumes another's output, or both write the same file or resource.

Before each response, list every call whose inputs you already hold, across reads, searches, subagents, and commands, and issue them all in that response. Hold a call back only when you can name the call it must follow; habit, tidiness, or "one step at a time" is not a dependency.