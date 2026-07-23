"""The agentic evaluation loop: extract -> classify (Primary) -> validate (Critic).

Design principle (the moat): the LLM never holds authority over money. The
deterministic 3-way match decides what is wrong; the Primary Agent only proposes
a disposition and explains it; a hard guardrail forbids auto-approving anything
the matcher flagged; and the Critic checks the Primary's reasoning for
consistency without ever re-deciding.
"""
