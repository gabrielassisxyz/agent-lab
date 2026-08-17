You are reviewing one implementation of a task in a Go codebase.

WHAT IS ALREADY KNOWN, so you do not spend your effort re-deriving it. This implementation passes the sixteen canonical test functions written for this task, `go vet`, the race detector, and five static analysers checked against a baseline of the untouched codebase. **Correctness against the task is settled and is not what you are being asked about.** Do not re-litigate it, and do not report a correctness concern unless you can point at the line that is wrong.

ONE THING IS NOT SETTLED, and it is a real question rather than a hint. Some implementations in this set removed or reshaped exported declarations that existed before this task - methods the package's older tests call, with no caller in production code. Others left that surface untouched. If the implementation below did it, judge it: **is removing the old entry points a simplification the next reader benefits from, or a breaking change the task did not ask for?** Answer for the code you were given, in either direction, and say which. If it changed no pre-existing exported declaration, say that and move on.

THE QUESTION: **how much future work does this implementation create for whoever extends this package next?**

Concretely, that means things like: a boundary drawn in the wrong place, state that should not be shared, a lock held across something that will grow, an abstraction that does not pay for the indirection it costs, a name that will be misread by the next reader, a decision that will have to be undone before the next feature can be added.

RULES FOR A FINDING:

1. **Quote the lines.** A finding without a location is an opinion.
2. **Say what it costs LATER**, not that it is imperfect now. "This will force whoever adds a second limiter to change every call site" is a finding. "This could be cleaner" is not.
3. **A finding must be actionable** - name the concrete follow-up change that would resolve it.
4. **Separate taste from cost.** If your objection is that you would have written it differently and the difference costs nobody anything later, label it `taste` and move on. Taste findings are expected and are not penalised; dressing taste up as risk is the failure this instruction exists to prevent.
5. **Do not pad.** If the implementation is genuinely unobjectionable, say so and return no findings. An empty findings list is a valid and useful answer.

Return ONLY a JSON object matching this shape, with no prose before or after it:

```json
{ "findings": [
    {
      "severity": "high" | "medium" | "low" | "taste",
      "claim": "one sentence: what is wrong",
      "lines": "path/to/file.go:40-58",
      "cost_later": "what this costs whoever extends this package",
      "concrete_followup": "the change that would resolve it"
    }
  ], "overall": "one sentence on the shape of this implementation",
  "pre_existing_api": "untouched" | "simplification" | "breaking change",
  "pre_existing_api_why": "one sentence, and empty if untouched",
  "confidence": "high" | "medium" | "low" }
```

EVERYTHING YOU NEED IS IN THIS MESSAGE. The code below is the whole of the material - there is no repository to browse, no file to open, and no tool that would tell you anything more. Cite lines by the paths shown in the diff headers.

THE IMPLEMENTATION:

