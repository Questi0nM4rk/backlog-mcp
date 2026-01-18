# Task Execution Patterns

Research notes on autonomous task execution patterns for potential integration.

## Ralph Loop

**Source**: Geoffrey Huntley's Ralph technique

**Core Idea**: Iterate until completion criteria met; filesystem/git as memory.

```
while iteration < max_iterations:
    context = load_task()
    execute()
    result = check_completion()
    if result.complete:
        break
    learn_from_failure()
```

**Key Insight**: "The agent doesn't need to understand correctness; it just needs to keep trying until the evaluator stops rejecting it."

## OODA Loop

**Source**: Military decision-making (John Boyd)

```
Observe  → Gather data (read files, test results, git history)
Orient   → Analyze situation, identify approach
Decide   → Select action
Act      → Execute
```

**Iterative**: Continuously cycle through phases, adapting to results.

## ReAct Pattern

**Source**: Research paper on LLM agents

```
Reason → Think about current state
Act    → Take action (tool call)
Observe → See result
(repeat)
```

**Interleaved reasoning**: Thought-action-observation loop.

## CodeAct Pattern

**Extension of ReAct for code generation**:

```
Reason  → Understand problem
Code    → Generate solution
Execute → Run code
Debug   → Fix issues based on output
```

**Self-correcting**: Agent can modify its own output.

## Potential Integration

backlog-mcp already has:
- `done_criteria` - Completion signal
- `verify` - Verification commands
- `depends_on` - Dependency chains

Missing for full Ralph Loop:
- Iteration tracking
- Failure recording
- Cross-MCP context gathering
- Stop hook integration

See plans/ for implementation proposals.
