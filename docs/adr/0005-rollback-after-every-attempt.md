# Roll back after every failed Attempt, not only at the end

The subject only requires that the Target Project be restored after the last of three failed Attempts. We roll back after **each** failed Attempt instead, so every Attempt patches the original code, and the model sees its previous Patch plus the error as text rather than on disk. This needs only one Snapshot per Attempt (of the files that Attempt touches), whereas stacking Attempts would need to track the union of every file touched across all of them to guarantee a byte-for-byte final restore. A Sanity Check refusal also counts as a failed Attempt.

## Considered Options

- Stacking Attempts on top of each other and rolling back once at the end: the model fixes its own code in place, but the Snapshot bookkeeping is harder to get exactly right, and a partial rollback fails the subject.
