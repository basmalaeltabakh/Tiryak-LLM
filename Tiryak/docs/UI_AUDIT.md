# Tiryak — UI/Integration Audit — Known Issues

## Retrieval confidence over-reports on weak/off-topic matches (found 2026-08-18)

**Symptom:** A prescription-scan query for Panadol (generated question: `"في
محاذير أو تفاعلات مهمة لازم أعرفها عن: Panadol؟"`) returned
`confidence.retrieval_confidence: "high"` and
`confidence.grounding_verdict: "grounded"`, but 3 of the 5 `evidence_panel`
chunks were bibliography/copyright/front-matter boilerplate (e.g. "Third-party
materials. If you wish to reuse material from this work...", a page-1
"Overview" section) with no clinical content about Panadol. The other 2 chunks
were about unrelated antibiotics (Cefiderocol, Plazomicin) pulled from the WHO
AWaRe book. The guideline corpus doesn't cover paracetamol/Panadol at all —
the model's answer correctly said so in prose — but the confidence badges told
the opposite story.

**Why it matters:** The UI shows a "High confidence" / "Grounded" badge next
to an answer that is, in substance, "not in my sources." If a pharmacist
learns to trust that badge, the same failure mode on a case where the
retrieved front-matter noise *looks* superficially relevant could produce a
confidently-badged wrong answer.

**Likely mechanism (not verified, not fixed):**
`compute_retrieval_confidence()` (`app/rag/confidence.py`) buckets confidence
purely off average cosine distance across the top-k chunks, with no
topicality/relevance check — bibliography and front-matter chunks can sit at
low embedding distance from a generic clinical-sounding query without being
topically relevant to it. Separately, `verify_answer_grounding()` graded the
answer "grounded," which may be locally correct (the answer's claim that "the
sources don't cover this" is itself grounded) — the misleading signal is
specifically `retrieval_confidence`, not the grounding verdict.

**Scope note:** `app/rag/` and `app/embeddings/` are off-limits per current
project constraints (retrieval layer is stable and eval-measured). Logged here
for future follow-up — not fixed as part of this pass.
