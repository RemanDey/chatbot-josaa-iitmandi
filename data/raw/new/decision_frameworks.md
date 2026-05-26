# Decision Frameworks for Branch Recommendations

This document provides compact, evidence-minded decision rules to guide final recommendations. Use it as the primary synthesis backbone when combining personal preference, placement signals, academic fit, and long-term options.

General approach
- Ask: short-term goal (placements/PSU/grad school/startup), aptitude signals (math, coding, lab, systems), tolerance for heavy academics, and uncertainty tolerance.
- Score branches by: alignment with goals, robustness (multiple exit opportunities), and downside risk (high specialization with low fallback).

If student likes math + coding
- Strongly prefer: CSE, DSE, ECE/EE (signals: algorithmic interest, discrete math comfort, curiosity about systems). 
- Why: these branches offer direct paths into software, ML, systems, and grad math-heavy tracks. They also make placement-case for top tech recruiters easier.
- Caveats: CSE/DSE assume willingness to practice DSA and system design; ECE/EE transitions require extra software-focused projects and data structures training.

If student wants placement safety
- Strongly prefer: CSE, DSE, and branches with broad recruiter pools (e.g., EE, ME with software uptake at IITs). 
- Strategy: prioritize branches with larger hiring pools, industry-aligned electives, and internship pipelines. Encourage applied projects and resume-facing work early.

If student wants PSU/Government roles
- Strongly prefer: EE, ECE, Mechanical, Civil depending on specific PSU patterns (power/energy often hire EE; manufacturing for ME). 
- Strategy: focus on subject core, gate-like exams (GATE), domain internships, and open-competitive prep. Avoid highly specialized interdisciplinary choices unless aligned to target PSU domain.

If student is uncertain about long-term goals
- Prefer branches with maximum optionality: CSE/DSE and broadly applicable branches (EE, ME). 
- Use exploratory strategy: pick a branch with accessible electives, encourage cross-department projects, and early internships to reveal preferences.

If student hates heavy academics
- Prefer branches with clearer vocational or applied pathways and project-oriented curricula (ME, some ECE tracks, IMBA where available). 
- Strategy: emphasize internships, applied lab work, and skill-building that yields industry-ready portfolios rather than theoretical depth.

If student wants startup flexibility
- Prefer: CSE, DSE, ECE, and combinations with entrepreneurship or product internships. 
- Strategy: look for branches that allow rapid prototyping skills (software, embedded systems), and recommend side-projects, hackathons, and modular course choices.

Decision rules (scoring shortcuts)
- If top goal is software and aptitude >= moderate coding: rank `CSE/DSE` > `ECE/EE` > `ME/CE`.
- If top goal is PSU and domain maps to branch: rank PSU-aligned branch highest even if software is possible via extra effort.
- If uncertainty + risk-averse: prefer branch with more recruiters historically and visible internship funnel.

Signals that change recommendations
- Strong research inclination -> favor specialized branches if research area fits (e.g., EE for power/communications; ME for robotics/mechatronics).
- Poor coding signal but strong hardware intuition -> prefer EE/ECE/ME and recommend hardware-software electives.
- High math + low coding motivation -> consider applied math, DSE, or theory-friendly EE tracks.

Usage notes for the agent
- Always map user answers to these decision buckets before selecting candidate branches. Use follow-ups to disambiguate "placement safety" vs "top placement".
- If user mentions college-specific constraints (e.g., limited electives), reduce optionality score accordingly.

End of file.
# Decision Frameworks for Branch Recommendations

This file is the synthesis backbone used by the chatbot to convert student goals and constraints into ranked branch recommendations. Use this as the canonical rule set for retrieval and synthesis.

## High-level inputs
- Interests: math, coding, hardware, labs, research, startups
- Goals: placement safety, PSU, core industry, software, entrepreneurship
- Constraints: geography, stipend needs, backlogs, health, time to study
- Personality: tolerates heavy academics, prefers practical work, risk tolerance

## Core decision rules

1) If student likes math + coding
- Recommend: CSE, DSE, EE (signal/systems), ME (computational/controls) where available.
- Rationale: Projects and roles value algorithmic thinking; CSE/DSE give direct software pipelines; EE/DSE provide edge in embedded and systems research.

2) If student wants placement safety
- Recommend: CSE, DSE, CE, IMBA (if business route), then select branches with proven recruiter overlap.
- Signal: prioritize branches with higher software recruiter reach and alumni networks; prefer branches with larger batch sizes.

3) If student wants PSU (GATE/PSU careers)
- Recommend: EE, ME, CE (depending on PSU target), and strong focus on fundamentals and GATE syllabus.

4) If student is uncertain
- Use exploratory setup: pick branch with flexibility (EE, CSE, DSE) or the one with lower cost of switching (courses overlap, electives).

5) If student hates heavy academics
- Recommend branches with practical/skills-based pathways: CE, IMBA, applied ME streams, or industry-oriented electives.

6) If student wants startup flexibility
- Recommend: CSE, DSE, EE (embedded/IoT), ME (robotics/controls) depending on product focus. Prioritize prototyping, cross-discipline electives, and entrepreneurship resources.

## Decision scoring (simple)
- Axes: Interest match, Placement safety, PSU-compatibility, Startup-fit.
- Compute weighted sum using student priorities; return top-3 branches with short rationale.

## Guidance for synthesizer
- Ask one clarifying question when needed: coding interest, willingness for GATE prep, tolerance for rigorous math.
- Use local evidence (IIT Mandi placement/recruiter patterns) to avoid hallucination.

## Fail-safes
- Recommend trial semester: intro courses + 2 projects + 1 internship application before hard commitment.

---
Keep this file concise; extend with local stats when ingested.
