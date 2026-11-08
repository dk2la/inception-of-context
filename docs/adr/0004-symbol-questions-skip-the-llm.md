# Symbol questions are answered from the Index, without the LLM

`/ask` is graded on not hallucinating symbols, and a 3B model invents functions even when told not to. Questions of the shape "is there a function X?" and "what functions are in file Y?" are therefore detected with a regex router and answered directly from Index metadata (symbol names, kinds, files, lines); the LLM is never called for them. Every other Question still goes to the model, along with a `KNOWN SYMBOLS` block listing the real symbols of the retrieved files.

## Consequences

Phrasings the router does not recognise fall through to the LLM path, so the router's patterns (English and Russian) are part of what keeps `/ask` truthful and should grow when a new phrasing slips through.
