"""AI trading layer (plan 03-01): AI proposes, deterministic code disposes.

- ``schema``   strict JSON parsing of model output (AIProposal/RegimeAssessment)
- ``base``     AIClient interface every provider implements
- ``mock``     offline deterministic provider + JSONL audit wrapper
- ``deepseek`` DeepSeek provider (OpenAI-compatible, stdlib-only)
- ``context``  pure market-context builders (what the model is allowed to see)
- ``prompts``  prompt-template loading/rendering (prompts/*.txt)
- ``gate``     pure deterministic gate over proposals
- ``engine``   AIEngine(LiveEngine): daily regime + on-setup proposal gate
- ``backtest`` run_ai_backtest: raw-vs-gated replay over history
"""
